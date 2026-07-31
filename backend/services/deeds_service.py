"""
DEEDS — permanent one-line records of a hero's accomplishments.

Extracted from real combat results (the log + structured fields already
know every dramatic moment), stored forever, shown in Hero Detail — and a
dead hero's deeds remain, so the Memorial can tell their story.

Kept intentionally selective: max 2 deeds per hero per fight, priority-
ordered, exact-duplicate texts skipped — a deed should feel EARNED, not
like a combat log with delusions of grandeur.
"""
import re

MAX_DEEDS_PER_FIGHT = 2


def _ensure_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hero_deeds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hero_id INTEGER NOT NULL,
            deed TEXT NOT NULL,
            floor INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


# A weapon good enough to be remembered is good enough for its maker to be
# remembered with it. Same gate as record_craft_deed — an iron dagger that
# happens to be held during a boss kill is not a smith's life's work.
CHAINED_DEED_RARITIES = {"Legendary", "Mythic", "Ascended"}


def _credit_the_smith(conn, wielder_id: int, deed_text: str, floor_number: int) -> list[dict]:
    """Reflect a hero's deed back onto whoever forged the weapon they did it with.

    Done here, from the wielder's id, rather than by threading a maker id
    through the combat stat pipeline — the deed parser already knows who did
    what, and equipment.is_equipped_to already knows what they were holding,
    so the join costs one query and touches no combat code.

    The point is the Blacksmith who never leaves the base. They can't earn a
    boss kill, but the blade that landed it was theirs, and the Memorial
    should say so.
    """
    try:
        row = conn.execute(
            """SELECT e.name, e.rarity, e.crafted_by, h.name AS smith_name
               FROM equipment e
               JOIN heroes h ON h.id = e.crafted_by
               WHERE e.is_equipped_to = ? AND e.type = 'Weapon'
                 AND e.crafted_by IS NOT NULL AND e.crafted_by != ?
               LIMIT 1""",
            (wielder_id, wielder_id),
        ).fetchone()
        if not row or row["rarity"] not in CHAINED_DEED_RARITIES:
            return []

        wielder = conn.execute("SELECT name FROM heroes WHERE id = ?", (wielder_id,)).fetchone()
        wielder_name = wielder["name"] if wielder else "someone"
        # The smith's version names the wielder and the weapon, not the blow —
        # they weren't there, and a deed that pretended otherwise would read
        # as a lie on their page.
        text = f"Forged {row['name']}, which {wielder_name} carried on floor {floor_number}"

        dup = conn.execute("SELECT 1 FROM hero_deeds WHERE hero_id = ? AND deed = ?",
                           (row["crafted_by"], text)).fetchone()
        if dup:
            return []
        conn.execute("INSERT INTO hero_deeds (hero_id, deed, floor) VALUES (?,?,?)",
                     (row["crafted_by"], text, floor_number))
        return [{"hero_id": row["crafted_by"], "deed": text, "chained": True}]
    except Exception as e:
        print(f"Chained smith deed error: {e}")
        return []


def record_deeds(conn, result: dict, floor_number: int, is_boss: bool, is_miniboss: bool) -> list[dict]:
    """Mine a winning combat result for deed-worthy moments. Returns the
    deeds written (for the result payload / toasts). Fail-safe: [] on error."""
    try:
        if result.get("winner") != "heroes":
            return []
        _ensure_schema(conn)
        log = result.get("log", [])
        survivors = result.get("surviving_heroes", [])
        init_heroes = {h["id"]: h for h in result.get("initial_state", {}).get("heroes", [])}
        enemy_names = [e["name"] for e in result.get("initial_state", {}).get("enemies", [])]
        rounds = result.get("rounds", 0)
        log_text = "\n".join(log)

        # Candidate deeds per hero, ordered by drama (priority first).
        candidates = {}  # hero_id -> [deed_text, ...]
        def add(hid, text):
            candidates.setdefault(hid, []).append(text)

        name_to_id = {h["name"]: hid for hid, h in init_heroes.items()}
        boss_name = enemy_names[0] if enemy_names else "the enemy"
        metrics = result.get("combat_metrics", {}) or {}
        survivor_ids = {s["id"] for s in survivors}
        top_dealer = max((hid for hid in metrics if hid in survivor_ids),
                         key=lambda hid: metrics[hid], default=None)

        # 1. Prophet's foresight — dodged literal death.
        for m in re.finditer(r"foresaw this — (.+?) steps aside", log_text):
            hid = name_to_id.get(m.group(1))
            if hid:
                add(hid, f"Stepped aside from certain death on floor {floor_number} — the Prophet's warning held true")

        # 2. Undying Will — refused a fatal blow.
        for m in re.finditer(r"(.+?) refuses to fall! \(Undying Will\)", log_text):
            hid = name_to_id.get(m.group(1).strip().lstrip("✦ ").strip())
            if hid:
                add(hid, f"Refused to die on floor {floor_number}")

        # 3. Boss / miniboss felled — top damage dealer gets the killing credit,
        #    every other survivor stood against it.
        if is_boss:
            if top_dealer is not None:
                add(top_dealer, f"Felled {boss_name} — floor {floor_number}")
            for s in survivors:
                if s["id"] != top_dealer:
                    add(s["id"], f"Stood against {boss_name} and lived — floor {floor_number}")
        elif is_miniboss and top_dealer is not None:
            add(top_dealer, f"Slew {boss_name} — floor {floor_number}")

        # 4. Survived a boss cataclysm.
        if "CATACLYSM" in log_text and is_boss:
            for s in survivors:
                add(s["id"], f"Weathered the cataclysm of {boss_name} — floor {floor_number}")

        # 5. Elite slain (affixed name in the roster).
        from services.combat_service import ELITE_AFFIXES
        elite = next((n for n in enemy_names if any(n.startswith(a + " ") for a in ELITE_AFFIXES)), None)
        if elite and top_dealer is not None and not is_boss:
            add(top_dealer, f"Cut down the {elite} — floor {floor_number}")

        # 6. Survival swarm outlasted.
        if result.get("is_survival_swarm"):
            for s in survivors:
                add(s["id"], f"Held the line for {rounds} rounds against the swarm — floor {floor_number}")

        # 7. Retrieval runner came through.
        if result.get("is_retrieval") and result.get("runner_survived") and result.get("runner_id") in survivor_ids:
            add(result["runner_id"], f"Carried the objective through floor {floor_number} untouched by death")

        # 8. Killing spree in a single fight.
        for s in survivors:
            if (s.get("kills_gained") or 0) >= 4:
                add(s["id"], f"Cut down {s['kills_gained']} foes in a single battle — floor {floor_number}")

        # 9. Death's door — walked out under 8% health.
        for s in survivors:
            mx = init_heroes.get(s["id"], {}).get("max_health") or 0
            if mx and 0 < s["health"] <= mx * 0.08:
                add(s["id"], f"Crawled off floor {floor_number} at death's door")

        # Write, capped + deduped.
        written = []
        for hid, texts in candidates.items():
            if hid < 0:  # constructs/NPC units
                continue
            existing = {r["deed"] for r in conn.execute(
                "SELECT deed FROM hero_deeds WHERE hero_id = ?", (hid,)).fetchall()}
            for text in texts[:MAX_DEEDS_PER_FIGHT]:
                if text in existing:
                    continue
                conn.execute("INSERT INTO hero_deeds (hero_id, deed, floor) VALUES (?,?,?)",
                             (hid, text, floor_number))
                written.append({"hero_id": hid, "deed": text})
                written.extend(_credit_the_smith(conn, hid, text, floor_number))
        return written
    except Exception as e:
        print(f"Deed recording error: {e}")
        return []


# ── Deeds away from the Tower ───────────────────────────────────────────────
#
# Everything above mines combat, which meant a hero's permanent record could
# only ever be a list of battles. A Blacksmith who never left the base died
# with an empty Memorial page no matter how long they'd served — the ledger
# had no way to say who someone WAS, only what they killed.
#
# These are deliberately rarer than combat deeds. A deed has to be earned, and
# "cooked a meal" is not a life event; the thresholds below are set so a base
# deed marks a peak, not a shift at work.

def record_base_deed(conn, hero_id: int, text: str, floor_number: int = None) -> dict | None:
    """Write one non-combat deed. Same dedupe rule as combat deeds — a hero
    who forges twenty fine blades has one deed about forging fine blades.
    Fail-safe: None on error or duplicate, never raises into a base action."""
    try:
        if hero_id is None or hero_id < 0 or not text:
            return None
        _ensure_schema(conn)
        dup = conn.execute(
            "SELECT 1 FROM hero_deeds WHERE hero_id = ? AND deed = ?", (hero_id, text)
        ).fetchone()
        if dup:
            return None
        conn.execute("INSERT INTO hero_deeds (hero_id, deed, floor) VALUES (?,?,?)",
                     (hero_id, text, floor_number))
        return {"hero_id": hero_id, "deed": text}
    except Exception as e:
        print(f"Base deed recording error: {e}")
        return None


# Rarity is the gate for craft deeds: an iron dagger is a Tuesday, a legendary
# blade is a life's work. Keeping the threshold here rather than at each call
# site means one place decides what counts as remarkable.
CRAFT_DEED_RARITIES = {"Legendary", "Mythic", "Ascended"}


def record_craft_deed(conn, smith_id: int, item_name: str, rarity: str) -> dict | None:
    """The smith remembers making something extraordinary."""
    if rarity not in CRAFT_DEED_RARITIES:
        return None
    return record_base_deed(conn, smith_id, f"Forged {item_name} — {rarity.lower()} work")


def record_teaching_deed(conn, teacher_id: int, student_name: str, milestone: str) -> dict | None:
    """A trainer's record of someone else's breakthrough."""
    return record_base_deed(conn, teacher_id, f"Taught {student_name}, who {milestone}")


def record_healing_deed(conn, medic_id: int, patient_name: str) -> dict | None:
    """Pulling someone back from the edge is the Infirmary's version of a boss kill."""
    return record_base_deed(conn, medic_id, f"Brought {patient_name} back from the brink")


def record_feast_deed(conn, cook_id: int, dish: str) -> dict | None:
    """Only for a cook whose work actually carried a climb."""
    return record_base_deed(conn, cook_id, f"Set the table with {dish} before the climb")


def get_hero_deeds(conn, hero_id: int) -> list[dict]:
    _ensure_schema(conn)
    rows = conn.execute(
        "SELECT deed, floor, created_at FROM hero_deeds WHERE hero_id = ? ORDER BY id DESC LIMIT 60",
        (hero_id,)).fetchall()
    return [dict(r) for r in rows]
