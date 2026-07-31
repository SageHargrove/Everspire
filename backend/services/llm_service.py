import os
import json
import re
import random
import concurrent.futures
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# Claude/Haiku is the ONLY text-generation provider — hero bios, combat
# narration, event text, zone themes, boss naming, legacy text, lore
# entries, creative-craft flavor, chatter. (Gemini was removed 2026-07-19:
# Haiku reads better and is cheaper; the API key is entered in-game via
# Settings -> AI, which is what powers all of this.)
CLAUDE_CHAT_MODEL = "claude-haiku-4-5-20251001"

# Anthropic clients are built lazily and cached per-key, so the key the
# player enters in Settings takes effect immediately without a restart (and
# a changed key rebuilds the client). Falls back to the ANTHROPIC_API_KEY
# env var for dev — see routers.settings.get_llm_api_key.
_anthropic_clients: dict = {}

def _get_anthropic_client():
    from routers.settings import get_llm_api_key
    key = get_llm_api_key()
    if not key:
        return None
    client = _anthropic_clients.get(key)
    if client is None:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        _anthropic_clients[key] = client
    return client

def generate_with_claude(prompt: str, max_tokens: int = 600, temperature: float = 0.9) -> str:
    """Raises on failure (no key configured, or the call itself errors) —
    callers already tolerate this: hero enrichment keeps the placeholder
    identity, flavor text uses its local fallback, chatter is skipped."""
    client = _get_anthropic_client()
    if client is None:
        raise RuntimeError("No Claude API key configured — set one in Settings -> AI.")
    response = client.messages.create(
        model=CLAUDE_CHAT_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()

# Tower combat resolution must never block on flavor text (zone theme, boss
# naming, narration) — none of it affects combat math. Calls submitted here
# keep running in the background even after a timeout; we just stop waiting
# on them and use a fallback instead.
_flavor_text_pool = concurrent.futures.ThreadPoolExecutor(max_workers=8)

def call_with_timeout(fn, *args, timeout=2.5, fallback=None, **kwargs):
    return await_flavor_text(submit_flavor_text(fn, *args, **kwargs), timeout=timeout, fallback=fallback)

def submit_flavor_text(fn, *args, **kwargs):
    """Kick off a flavor-text call in the background without waiting — pair with
    await_flavor_text() once the result is actually needed. Lets independent
    calls (e.g. zone theme + boss naming) run concurrently instead of stacking
    into a sequential wait."""
    return _flavor_text_pool.submit(fn, *args, **kwargs)

def await_flavor_text(future, timeout=1.5, fallback=None):
    try:
        return future.result(timeout=timeout)
    except Exception:
        return fallback

RARITY_FLAVOR = {
    1: "a common peasant, laborer, or wanderer with humble origins",
    2: "a minor adventurer or soldier with some experience",
    3: "a seasoned fighter, skilled craftsman, or minor mage",
    4: "an elite warrior, veteran commander, or powerful spellcaster",
    5: "a legendary hero, archmage, or noble champion",
    6: "a near-mythic figure, ancient warrior, or transcendent being",
    7: "an impossibly rare entity — a demigod, an immortal, or a living legend",
}


from services.ego_service import BATTLE_TENDENCIES


class HeroProfile(BaseModel):
    name: str
    title: str
    backstory: str
    personality: str
    gender: str
    portrait_prompt: str
    ego_type: str | None = None
    battle_tendency: str = "Stoic"




def _generate_with_claude_fallback(prompt: str, max_tokens: int = 600, temperature: float = 0.9) -> str:
    """The single entry point every generate_* function below calls. Now a
    thin wrapper over Claude/Haiku (Gemini fallback removed 2026-07-19). On
    failure it raises — callers already handle that path (hero enrichment
    keeps its placeholder, flavor uses call_with_timeout's fallback, chatter
    is skipped), which is exactly how the game behaved before with no keys."""
    return generate_with_claude(prompt, max_tokens=max_tokens, temperature=temperature)


def _clean_json(raw: str) -> str:
    """Strip markdown fences if model adds them."""
    raw = re.sub(r'^```json\s*', '', raw)
    raw = re.sub(r'^```\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    return raw.strip()


def generate_hero_profile(birth_star: int, aptitudes: dict, extra_prompt: str = "", fixed_name: str = None) -> HeroProfile:
    # fixed_name: when the hero ALREADY has a permanent name (the re-enrichment
    # / reconcile path — the player has already seen it, so it can't change),
    # the backstory MUST be written about that exact person. Otherwise the LLM
    # invents a fresh name for the story while the card keeps the old one, and
    # the Chronicle ends up narrating a stranger ("Zaina was born…" on a hero
    # named Elara). We instruct the model to use the fixed name and then force
    # it regardless of what the model returned.
    apt_names = {
        "apt_combat": "combat prowess",
        "apt_tactical": "tactical genius",
        "apt_survival": "survival instinct",
        "apt_mental": "mental fortitude",
        "apt_leadership": "leadership presence",
    }
    top_apt = max(aptitudes, key=aptitudes.get)
    top_apt_label = apt_names.get(top_apt, "unknown gift")

    heterochromia_rule = "" if birth_star >= 5 else "CRITICAL RULE: Heterochromia (two-colored eyes) is explicitly FORBIDDEN. "

    ego_instruction = (
        "For ego_type: this hero may have an Ego (an awakened trait) only because birth_star >= 4. Grant one ONLY if "
        "their personality strongly warrants it. If so, set ego_type to exactly one of: \"Aggressive\", \"Cautious\", "
        "\"Tactical\", \"Leader\". Otherwise set ego_type to the JSON literal null (NOT the string \"null\")."
    ) if birth_star >= 4 else (
        "This hero's birth_star is below 4, so ego_type MUST be the JSON literal null — NOT the string \"null\", "
        "not an empty string, the actual JSON null value with no quotes."
    )

    # Gemini reliably mode-collapses onto "Kael/Kaelen/Kaelan"-style names when
    # asked for "varied fantasy names" repeatedly in a short window — pulling
    # recently-used names and banning them, plus naming the specific attractor
    # tokens directly, is what actually breaks the loop.
    avoid_names_clause = ""
    try:
        from database import db
        with db() as conn:
            recent = conn.execute("SELECT name FROM heroes ORDER BY id DESC LIMIT 25").fetchall()
        recent_names = [r["name"] for r in recent if r["name"]]
        if recent_names:
            avoid_names_clause = (
                "\nDo NOT use any of these already-taken names, or close variants of them "
                f"(e.g. swapping one letter): {', '.join(recent_names)}."
            )
    except Exception:
        pass

    fixed_name_clause = ""
    if fixed_name:
        fixed_name_clause = (
            f"\n\nCRITICAL — THIS HERO'S NAME IS ALREADY FIXED as \"{fixed_name}\". "
            f"You are ONLY writing their lore. Set the \"name\" field to exactly \"{fixed_name}\", "
            f"and write the title, backstory, and personality about a person named \"{fixed_name}\" — "
            f"wherever the story names them, use \"{fixed_name}\" (or their first name from it). "
            f"Do NOT invent any other name for this character."
        )

    prompt = f"""You are generating a hero for a dark fantasy roguelike tower-climbing game.

Hero rarity: {birth_star}★ — {RARITY_FLAVOR[birth_star]}
This hero has a notable hidden gift in: {top_apt_label} (do NOT state this directly — hint at it through personality and backstory)
{extra_prompt}{fixed_name_clause}

Generate a hero profile. Be creative, grounded, and avoid clichés.
The world is dark, morally complex, and dangerous. Heroes are people, not archetypes.
IMPORTANT for the name: you have a strong, well-documented bias toward "Kael", "Kaelen", "Kaelan", "Cael", and similarly-rooted names — DO NOT use any of these or close variants. Also avoid other overused fantasy-name tropes (Elara, Aria, Lyra, Nyx, Seraphina). Pull from genuinely diverse real-world naming traditions (e.g. West African, East Asian, Slavic, Mediterranean, South Asian, Polynesian, Celtic) reimagined for this setting, and vary which tradition you draw from each time.{avoid_names_clause}
IMPORTANT for portrait_prompt: {heterochromia_rule}Describe ONLY the person — their body, face, hair and what they wear. Write nothing about lighting, mood, atmosphere, weather, time of day, background or surroundings. Measured across a generated roster, every single prompt that mentioned "candlelight" or "moonlight" caused the renderer to draw an actual candle or moon standing next to the hero, because it treats every noun as an object to place in frame. Describe a SPECIFIC, UNIQUE appearance. Vary ethnicities, skin tones, hair types, facial features, body types, and ages. Avoid defaulting to pale/white-haired/young characters. Include: specific hair color AND style, skin tone, a distinguishing facial feature, one unique detail (scar, tattoo, accessory, expression). Each hero should look completely different from the last.
IMPORTANT for ego_type: {ego_instruction}
IMPORTANT for battle_tendency: every hero, regardless of star rarity, has a battle_tendency — a lighter, universal trait describing their instinct in a fight (distinct from ego_type, which is rarer and only governs team-composition opinions). Pick exactly one of: "Reckless", "Calculating", "Protective", "Glory-Seeking", "Stoic", "Vengeful" — whichever best matches the personality you just wrote.
IMPORTANT for gender consistency: decide the hero's gender FIRST, then write the name, title, and backstory to match it. A male hero must never be called "princess", "queen", "maiden", "duchess", "her" etc. in the title/backstory/personality text, and a female hero must never be called "prince", "king", "lord", "duke", "him" etc. — unless the backstory is explicitly about that exact contradiction (e.g. a title forced on them against their identity) and says so outright in the text. Do not let "royal"/"exiled"/"noble" framing default to gendered nobility words that contradict the gender you picked.

Respond ONLY with valid JSON and nothing else — no markdown, no backticks, no preamble:
{{
  "name": "First and Last name (MUST have a surname to ensure absolute uniqueness. culturally varied — pull from diverse real-world naming traditions)",
  "title": "Short epithet or nickname (e.g. 'The Twice-Burned', 'Ash of the North')",
  "backstory": "8-12 sentences telling their full life story in order: origins, the wound or wonder that shaped them, how they came to the Tower, and what they still carry. Specific, evocative, no tropes. This is revealed to the player sentence by sentence as the hero ascends, so EVERY sentence should stand alone as a satisfying fragment, and later sentences should hold the deepest secrets.",
  "personality": "1-2 sentences. How they act under pressure.",
  "gender": "male, female, or other",
  "portrait_prompt": "anime portrait tags describing ONLY THE PERSON: specific hair color, hair style, skin tone, facial feature, clothing detail, expression. Must be visually distinct. Describe NO lighting, NO background, NO environment, NO scene, and NO held or nearby objects beyond their own clothing and gear — the renderer adds a black void and its own lighting, and any atmosphere you write here gets drawn as a literal prop.",
  "ego_type": null,
  "battle_tendency": "Stoic"
}}"""

    # max_tokens raised for the long-form chronicle (8-12 sentence backstory).
    raw = _generate_with_claude_fallback(prompt, max_tokens=1600, temperature=0.9)
    try:
        data = json.loads(_clean_json(raw))
    except json.JSONDecodeError:
        print(f"[LLM] JSON parse failed, raw response was:\n{raw}\nRetrying with strict JSON prompt...")
        retry_prompt = prompt + "\n\nIMPORTANT: Your previous response was not valid JSON, likely because it was cut off. Keep the backstory tighter (6-8 sentences). Respond with ONLY the raw JSON object. No markdown, no backticks, no explanation."
        raw = _generate_with_claude_fallback(retry_prompt, max_tokens=1600, temperature=0.7)
        data = json.loads(_clean_json(raw))

    # Models occasionally write the literal string "null" instead of JSON null
    # for ego_type — coerce it so it never ends up stored/displayed as text.
    if isinstance(data.get("ego_type"), str) and data["ego_type"].strip().lower() in ("null", "none", ""):
        data["ego_type"] = None

    if data.get("battle_tendency") not in BATTLE_TENDENCIES:
        data["battle_tendency"] = random.choice(BATTLE_TENDENCIES)

    # Force the fixed name regardless of what the model returned, so the card
    # name and the story it tells can never drift apart.
    if fixed_name:
        data["name"] = fixed_name

    return HeroProfile(**data)


def generate_combat_narration(combat_log: list, hero_names: list[str]) -> str:
    log_text = "\n".join([f"- {e}" for e in combat_log[-10:]])
    prompt = f"""You are narrating a battle in a dark fantasy roguelike game.
Heroes involved: {', '.join(hero_names)}

Combat events:
{log_text}

Write 3-5 sentences of vivid, highly descriptive, and grim narration.
Focus on the visceral sensory details of the battle — the sound of steel, the horrific nature of the enemies, the environment, and the emotional toll on the heroes.
Make the battle sound desperate, brutal, and cinematic. Be specific about the heroes' names and the actions in the log.
Describe it as if observing a tense turn-based battle unfold before your eyes, emphasizing the decisive blows, the weight of every strike, and near-misses.
Do not sugarcoat injuries or deaths. Respond with only the narration text, no preamble."""

    return _generate_with_claude_fallback(prompt, max_tokens=400, temperature=0.8)


def generate_turn_narrations(log_lines: list[str], hero_names: list[str]) -> list[str] | None:
    """Rewrites each raw per-turn combat log line (which always embeds exact
    damage numbers and HP fractions, e.g. 'X takes 47 damage [120/200]') into
    a short, numberless, action-focused line — same length, same order, so
    the frontend can swap line N in for turn N's raw log text as combat plays
    out. Returns None on any failure (mismatched length, bad JSON, etc.) so
    the caller can just keep showing the raw line instead."""
    if not log_lines:
        return None
    numbered = "\n".join([f"{i}: {line.strip()}" for i, line in enumerate(log_lines)])
    prompt = f"""You are rewriting a turn-by-turn combat log for a dark fantasy roguelike game.
Heroes involved: {', '.join(hero_names)}

Raw log lines (each already tells you who acted, who was hit, and whether it landed, killed, crit, or was dodged):
{numbered}

Rewrite EACH line into ONE short, punchy, grim sentence (under 14 words) describing the action itself —
the swing, the impact, the reaction — with NO exact numbers, NO damage figures, NO HP fractions.
Keep it specific to who's acting and who's being hit. Preserve whether it was a crit, a kill, a dodge, or a miss if the original line says so.
Return EXACTLY {len(log_lines)} lines, same order, one rewritten sentence per input line, nothing else.

Respond ONLY with a valid JSON array of {len(log_lines)} strings, no markdown, no preamble."""

    try:
        raw = _generate_with_claude_fallback(prompt, max_tokens=max(300, len(log_lines) * 30), temperature=0.85)
        lines = json.loads(_clean_json(raw))
        if isinstance(lines, list) and len(lines) == len(log_lines):
            return [str(l) for l in lines]
        return None
    except Exception as e:
        print(f"[LLM] Turn narration failed: {e}")
        return None


def generate_event_text(floor_number: int, event_type: str, context: str = "") -> dict:
    prompt = f"""You are generating a floor event for a dark fantasy roguelike.
Floor: {floor_number}, Event type: {event_type}
Context: {context or "Standard tower exploration."}

Respond ONLY with valid JSON and nothing else — no markdown, no backticks:
{{
  "title": "Short event name",
  "description": "2-3 sentence scene description. Grim, specific, atmospheric.",
  "choices": [
    {{"id": "a", "text": "Choice text", "hint": "Vague hint at consequence"}},
    {{"id": "b", "text": "Choice text", "hint": "Vague hint at consequence"}}
  ]
}}"""

    raw = _generate_with_claude_fallback(prompt, max_tokens=400, temperature=0.85)
    return json.loads(_clean_json(raw))


def generate_event_narrative(theme: str, floor_number: int, hero_names: list[str]) -> str:
    prompt = f"""You are narrating a floor event in a dark fantasy roguelike tower.
Floor: {floor_number}
Heroes present: {', '.join(hero_names)}
Event scenario: {theme}

Write 4-5 sentences of highly atmospheric, grim narration setting the scene.
Describe the environment in vivid detail (smells, sounds, lighting).
Make the situation feel tense, dangerous, and morally ambiguous.
The player will have to make a difficult, agonizing decision immediately after this. Make the consequences of their impending decision feel incredibly heavy, as if the heroes' lives depend on what you choose.
Be specific with hero names and their reactions to the eerie scene.
Respond with only the narration text."""
    return _generate_with_claude_fallback(prompt, max_tokens=200, temperature=0.85)


def generate_event_resolution_narrative(theme: str, choice_label: str, effects: dict, hero_names: list[str]) -> str:
    effects_text = ", ".join([f"{k}: {v}" for k, v in effects.items()])
    prompt = f"""You are narrating the outcome of a choice in a dark fantasy roguelike tower.
Event: {theme}
Choice made: {choice_label}
Mechanical effects: {effects_text}
Heroes: {', '.join(hero_names)}

Write 3-4 sentences narrating the visceral outcome of the choice.
If the effects are negative (loss of health, stress gained, trauma), describe the pain, horror, or regret vividly.
If the effects are positive, describe the fleeting relief or the grim satisfaction.
Be specific with hero names.
Grim, atmospheric, and highly descriptive. Respond with only the narration text."""
    return _generate_with_claude_fallback(prompt, max_tokens=200, temperature=0.8)


def generate_zone_theme(start_floor: int) -> str:
    prompt = f"""You are generating a dark fantasy zone theme for a roguelike tower.
This zone covers floors {start_floor} to {start_floor+9}.

Provide a single, short, highly evocative name for this zone, and 1 sentence describing its grim, terrifying atmosphere.
Format: "Name: Description"
Example: "The Bleeding Archives: Shelves of flesh-bound tomes whisper madness to those who walk the aisles."

Respond with only the zone name and description."""
    try:
        return _generate_with_claude_fallback(prompt, max_tokens=100, temperature=0.9).strip()
    except Exception:
        return "The Dark Unknown: Shadows obscure the path ahead."

def generate_hero_reaction(hero_name: str, hero_personality: str, event_type: str) -> str:
    """Generate a 1-sentence hero reaction to a game event."""
    event_prompts = {
        "team_added": "being assigned to a new team for the tower",
        "teammate_death": "watching a teammate die in front of them",
        "synthesis_witness": "watching the Master sacrifice another hero through synthesis",
        "rest": "finally getting a moment of rest after a brutal fight",
        "fear_stun": "being paralyzed by fear in the middle of combat",
        "promotion": "being promoted to a higher star rank",
        "boss_victory": "defeating a floor boss",
        "low_morale": "feeling broken and hopeless after too many losses",
        "high_trauma": "carrying unbearable trauma from everything they've witnessed",
    }
    context = event_prompts.get(event_type, event_type)
    prompt = f"""You are voicing a character in a dark fantasy roguelike tower.
Character: {hero_name}
Personality: {hero_personality}
Situation: {context}

Write ONE short sentence as the character's spoken reaction. In-character, emotional, dark tone.
Use first person. No quotes. No action tags. Just the dialogue line."""
    return _generate_with_claude_fallback(prompt, max_tokens=60, temperature=0.9)


def generate_legacy_text(hero_name: str, birth_star: int, floors: int, kills: int, backstory: str) -> tuple[str, str]:
    """Generate a legacy title and flavor text for a fallen hero."""
    prompt = f"""A hero has fallen permanently in a dark fantasy roguelike tower.

Name: {hero_name}
Star Rank: {birth_star}★
Floors Survived: {floors}
Enemies Slain: {kills}
Backstory: {backstory or 'Unknown origins.'}

Generate:
1. A short, evocative TITLE for their legacy (3-6 words, like "The Unbroken Shield" or "Echo of the Last Stand")
2. A brief FLAVOR TEXT (1-2 sentences) about what they meant and how they fell.

Format your response EXACTLY as:
TITLE: [title here]
FLAVOR: [flavor text here]"""
    try:
        text = _generate_with_claude_fallback(prompt, max_tokens=120, temperature=0.85)
        title_match = re.search(r"TITLE:\s*(.+)", text)
        flavor_match = re.search(r"FLAVOR:\s*(.+)", text)
        title = title_match.group(1).strip() if title_match else f"The Memory of {hero_name}"
        flavor = flavor_match.group(1).strip() if flavor_match else f"They fell in the tower, but their echo remains."
        return title, flavor
    except Exception:
        return f"The Memory of {hero_name}", f"They survived {floors} floors and slew {kills} foes."

def generate_boss_enemy(zone_theme: str, floor_number: int, is_miniboss: bool) -> dict:
    prompt = f"""
Generate a boss enemy for floor {floor_number} of a dark fantasy tower.
The current biome/zone theme is: "{zone_theme}".
This is a {"MINIBOSS" if is_miniboss else "MAJOR BOSS"}.
Return ONLY valid JSON in this format:
{{
  "name": "Boss Name",
  "modifier": "Adjective (e.g., Enraged, Vampiric, Armored, Cursed)",
  "hp_multiplier": 1.2,
  "atk_multiplier": 1.1,
  "def_multiplier": 0.9,
  "spd_multiplier": 1.0
}}
Keep multipliers between 0.7 and 2.0. The modifier should reflect the theme.
"""
    try:
        raw = _generate_with_claude_fallback(prompt, max_tokens=150, temperature=0.7)
        return json.loads(_clean_json(raw))
    except Exception as e:
        print(f"Failed to generate boss: {e}")
        return {
            "name": f"{zone_theme.split(',')[0]} Guardian" if zone_theme else "Guardian",
            "modifier": "Enraged",
            "hp_multiplier": 1.2, "atk_multiplier": 1.2, "def_multiplier": 1.0, "spd_multiplier": 1.0
        }

def generate_creative_craft(description: str, materials: dict, power_pool: int, crafter_level: int) -> tuple[dict, str, str]:
    prompt = f"""You are the master Blacksmith in the Tower.
    The crafter wants to build: {description}
    They used these materials: {materials}
    Their crafting power limit is: {power_pool}
    
    Determine the best item type (weapon, armor, accessory) and name it something cool. Also create a recipe description.
    Allocate stats based on the power limit (distribute {power_pool} points across base_str, base_int, base_hlt, base_agi, base_def, base_end, base_wil, base_luck).
    
    Return JSON EXACTLY like this:
    {{
        "recipe_name": "Name of the Recipe",
        "recipe_desc": "Flavor text for this recipe",
        "item_name": "Name of the Item",
        "type": "weapon",
        "base_str": 0,
        "base_int": 0,
        "base_hlt": 0,
        "base_agi": 0,
        "base_def": 0,
        "base_end": 0,
        "base_wil": 0,
        "base_luck": 0
    }}
    """
    
    resp = _generate_with_claude_fallback(prompt, max_tokens=300, temperature=0.85)
    try:
        import json
        data = json.loads(resp.strip().strip('`').replace('json', ''))
        
        equip = {
            "name": data.get("item_name", "Mysterious Craft"),
            "type": data.get("type", "accessory"),
            "rarity": "B", # Creative crafts are inherently better quality
            "level": crafter_level,
            "base_str": data.get("base_str", 0),
            "base_int": data.get("base_int", 0),
            "base_hlt": data.get("base_hlt", 0),
            "base_agi": data.get("base_agi", 0),
            "base_def": data.get("base_def", 0),
            "base_end": data.get("base_end", 0),
            "base_wil": data.get("base_wil", 0),
            "base_luck": data.get("base_luck", 0),
            "str_pct": 0.0, "int_pct": 0.0, "hlt_pct": 0.0, "agi_pct": 0.0, "def_pct": 0.0, "end_pct": 0.0, "wil_pct": 0.0, "luck_pct": 0.0, "regen_pct": 0.0
        }
        return equip, data.get("recipe_name", "Unknown Recipe"), data.get("recipe_desc", "A secret technique.")
    except Exception as e:
        # Fallback
        equip = {
            "name": "Failed Experiment",
            "type": "accessory",
            "rarity": "D",
            "level": crafter_level,
            "base_str": 0, "base_int": 0, "base_hlt": 0, "base_agi": 0, "base_def": 0, "base_end": 0, "base_wil": 0, "base_luck": 0,
            "str_pct": 0.0, "int_pct": 0.0, "hlt_pct": 0.0, "agi_pct": 0.0, "def_pct": 0.0, "end_pct": 0.0, "wil_pct": 0.0, "luck_pct": 0.0, "regen_pct": 0.0
        }
        return equip, "Failed Recipe", "The materials were ruined."


def generate_lore_entry(milestone: int, previous_titles: list[str], encounters: list[str] = None) -> tuple[str, str]:
    """One Lore Journal page, unlocked every 10th floor cleared. Mirrors
    chat_service._tower_era's escalation (early = pure confusion, later =
    a settled but still-unfolding mythology) so the Journal and hero
    chatter read as the same continuity, not two unrelated voices.

    `encounters` is THIS save's own floor_history rows since the prior
    milestone (what was actually fought/chosen) — woven in as the concrete
    detail the page is "about", so two different saves reaching the same
    milestone get genuinely different pages, not the same generic text.
    Returns (title, text)."""
    if milestone < 30:
        stage = (
            "This is early. Whatever truth the Tower holds is still completely "
            "obscured — write a fragment that raises more questions than it "
            "answers: an inscription, a corpse's final note, a half-glimpsed "
            "structure that shouldn't exist. No grand revelations yet."
        )
    elif milestone < 70:
        stage = (
            "The mystery is starting to take shape, but nothing is confirmed. "
            "Write a fragment that connects to or complicates what's likely "
            "been hinted at before, without fully resolving it."
        )
    else:
        stage = (
            "Deep into the Tower now. The fragments should be converging "
            "toward something — write a piece that feels like a real piece of "
            "the puzzle clicking into place, even if the full picture still "
            "isn't whole."
        )

    avoid = ""
    if previous_titles:
        avoid = "Previously revealed page titles (do NOT reuse these names or repeat their exact angle): " + ", ".join(previous_titles[-6:])

    encounter_block = ""
    if encounters:
        sample = "\n".join(encounters[-12:])
        encounter_block = (
            "What this specific party actually lived through on the floors covered by this page "
            f"(weave details from this in naturally — this page should feel like IT belongs to this "
            f"party's own climb, not a generic page any party would get):\n{sample}"
        )

    prompt = f"""You are writing one page of a slowly-unlocked lore journal for a dark fantasy roguelike tower.
This page unlocks after floor {milestone} has been cleared.

{stage}
{avoid}

{encounter_block}

Write a short, evocative journal page (4-6 sentences) — a found document, a carved inscription, a survivor's account, or a fragment of forbidden knowledge about the Tower itself: what it is, who built it, or why it exists. Dark, mysterious, literary in tone — not a stat readout, not addressed to "the player".

Respond in exactly this format with no extra commentary:
TITLE: <a short evocative title, 2-5 words>
TEXT: <the journal page text>"""
    try:
        raw = _generate_with_claude_fallback(prompt, max_tokens=220, temperature=0.95)
        title, text = "Untitled Page", raw.strip()
        for line in raw.splitlines():
            if line.strip().upper().startswith("TITLE:"):
                title = line.split(":", 1)[1].strip()
            elif line.strip().upper().startswith("TEXT:"):
                text = line.split(":", 1)[1].strip()
        return title, text
    except Exception:
        return f"Floor {milestone}", "The page is illegible — water damage has claimed whatever was written here."
