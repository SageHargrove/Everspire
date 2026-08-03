"""Guilds v1 — design: docs/guild-social-design.md (signed off
2026-07-06: "Guild" terminology, cap 20 -> upgradeable 50, 50k local founding
fee, no hero loans, weekly pledge banks / 4-week seasons later).

v1 scope: found/registry/apply/decide/leave, roster with ranks, daily
check-in (guild coin + pledge), daily shared-HP guild boss (3 strikes/day,
coin payout on kill), guild-coin shop with weekly per-member limits. Shop
purchases return a `grant` the buyer's client applies to its own save via
the local mail system — same client-side economy split as scouting fees.
"""
import json
import random
import time
from datetime import datetime, timezone

from fastapi import HTTPException

RANKS = ("MASTER", "OFFICER", "MEMBER")
BASE_MEMBER_CAP = 20
MAX_MEMBER_CAP = 50
CAP_UPGRADE_COST = 2000          # treasury coin per +10 members
CHECKIN_COIN = 5
CHECKIN_TREASURY = 10
BOSS_STRIKES_PER_DAY = 3
BOSS_KILL_COIN = 120
BOSS_TOP_BONUS_COIN = 80

# (name, hp per member) — the daily beast scales to the roster, so a
# 3-member guild and a 50-member guild both have a real (but earnable)
# daily kill. Tuned for ~3 solid strikes per member to fell it.
BOSSES = [
    ("The Ashen Leviathan", 300_000),
    ("The Hollow Choir", 250_000),
    ("Grave-Tide Amalgam", 350_000),
    ("The Pale Court's Champion", 325_000),
]

SHOP_ITEMS = {
    "seal_cache": {"name": "RARE SEAL CACHE", "desc": "A guaranteed 5★ summon, sealed in wax.", "cost": 800, "weekly": 1,
                   "grant": {"summon_ticket": "5-Star Summon Ticket"}},
    "aether_bundle": {"name": "AETHER BUNDLE", "desc": "Refined aether ×50 for the Mage Tower.", "cost": 450, "weekly": 3,
                      "grant": {"aether": 50}},
    "emberleaf_ration": {"name": "EMBERLEAF RATION", "desc": "Feeds a full squad before a climb.", "cost": 120, "weekly": 5,
                         "grant": {"ingredients": 40}},
    "refit_voucher": {"name": "SKYDOCK REFIT VOUCHER", "desc": "A pouch of gold for the Skydock's fitters.", "cost": 300, "weekly": 2,
                      "grant": {"gold": 12000}},
    "gilded_gems": {"name": "GILDED GEMS", "desc": "A pouch of 300 gems for the vault.", "cost": 500, "weekly": 2,
                    "grant": {"gems": 300}},
}


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _week() -> str:
    iso = datetime.now(timezone.utc).isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _seconds_to_utc_midnight() -> int:
    now = datetime.now(timezone.utc)
    return int(86400 - (now.hour * 3600 + now.minute * 60 + now.second))


def init_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS guilds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            motto TEXT,
            banner_json TEXT,
            founder TEXT,
            renown INTEGER DEFAULT 0,
            treasury INTEGER DEFAULT 0,
            member_cap INTEGER DEFAULT 20,
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS guild_members (
            guild_id INTEGER,
            username TEXT UNIQUE,
            rank TEXT DEFAULT 'MEMBER',
            joined_at REAL,
            guild_coin INTEGER DEFAULT 0,
            last_checkin TEXT,
            week_key TEXT,
            weekly_pledge INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS guild_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            username TEXT,
            message TEXT,
            status TEXT DEFAULT 'pending',
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS guild_boss (
            guild_id INTEGER,
            date TEXT,
            boss_name TEXT,
            max_hp INTEGER,
            hp INTEGER,
            killed INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, date)
        );
        CREATE TABLE IF NOT EXISTS guild_boss_strikes (
            guild_id INTEGER,
            date TEXT,
            username TEXT,
            strikes INTEGER DEFAULT 0,
            damage INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, date, username)
        );
        CREATE TABLE IF NOT EXISTS guild_shop_purchases (
            week_key TEXT,
            username TEXT,
            item_id TEXT,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (week_key, username, item_id)
        );
        CREATE TABLE IF NOT EXISTS allies (
            username_a TEXT,
            username_b TEXT,
            status TEXT DEFAULT 'pending',  -- pending: a invited b
            since REAL,
            PRIMARY KEY (username_a, username_b)
        );
        CREATE TABLE IF NOT EXISTS guild_perks (
            guild_id INTEGER,
            perk_id TEXT,
            level INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, perk_id)
        );
        CREATE TABLE IF NOT EXISTS guild_wars (
            week_key TEXT,
            guild_a INTEGER,
            guild_b INTEGER,             -- NULL = bye week (odd guild out)
            score_a INTEGER DEFAULT 0,
            score_b INTEGER DEFAULT 0,
            resolved INTEGER DEFAULT 0,
            PRIMARY KEY (week_key, guild_a)
        );
        CREATE TABLE IF NOT EXISTS guild_war_scores (
            week_key TEXT,
            guild_id INTEGER,
            username TEXT,
            score INTEGER DEFAULT 0,
            PRIMARY KEY (week_key, guild_id, username)
        );
    """)


# ─── The Lodge War — weekly guild vs guild (design: Guild War spec) ───
# "Every floor cleared and every arena bout won during the war window adds
# to your lodge's score. The winning lodge splits the spoils by
# contribution." Pairings form lazily on the week's first war query
# (adjacent renown), scoring rides existing actions, payout is lazy when a
# later week first looks at the board.

WAR_FLOOR_SCORE = 10      # per floor gained on the PvE ladder
WAR_BOUT_SCORE = 25       # per ranked bout won
WAR_WIN_TREASURY = 500
WAR_WIN_COIN = 40
WAR_LOSE_COIN = 10


def _seconds_to_next_monday() -> int:
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    days = (7 - now.weekday()) % 7 or 7
    nxt = (now + timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((nxt - now).total_seconds())


def _resolve_past_wars(conn):
    week = _week()
    for w in conn.execute("SELECT * FROM guild_wars WHERE resolved = 0 AND week_key < ?", (week,)).fetchall():
        conn.execute("UPDATE guild_wars SET resolved = 1 WHERE week_key = ? AND guild_a = ?",
                     (w["week_key"], w["guild_a"]))
        if w["guild_b"] is None:
            continue  # bye — no spoils, no scars
        if w["score_a"] == w["score_b"]:
            winner, loser = None, None  # a stalemate pays nobody
        elif w["score_a"] > w["score_b"]:
            winner, loser = w["guild_a"], w["guild_b"]
        else:
            winner, loser = w["guild_b"], w["guild_a"]
        if winner is None:
            continue
        conn.execute("UPDATE guilds SET treasury = treasury + ?, renown = renown + 15 WHERE id = ?",
                     (WAR_WIN_TREASURY, winner))
        conn.execute("UPDATE guild_members SET guild_coin = guild_coin + ? WHERE guild_id = ?",
                     (WAR_WIN_COIN, winner))
        conn.execute("UPDATE guild_members SET guild_coin = guild_coin + ? WHERE guild_id = ?",
                     (WAR_LOSE_COIN, loser))


def _ensure_war_pairings(conn, week: str):
    if conn.execute("SELECT 1 FROM guild_wars WHERE week_key = ? LIMIT 1", (week,)).fetchone():
        return
    _resolve_past_wars(conn)
    rows = conn.execute("SELECT id FROM guilds ORDER BY renown DESC, id ASC").fetchall()
    ids = [r["id"] for r in rows]
    for i in range(0, len(ids) - 1, 2):
        conn.execute("INSERT OR IGNORE INTO guild_wars (week_key, guild_a, guild_b) VALUES (?,?,?)",
                     (week, ids[i], ids[i + 1]))
    if len(ids) % 2 == 1:
        conn.execute("INSERT OR IGNORE INTO guild_wars (week_key, guild_a, guild_b) VALUES (?,?,NULL)",
                     (week, ids[-1]))


def _war_of(conn, week: str, guild_id: int):
    return conn.execute(
        "SELECT * FROM guild_wars WHERE week_key = ? AND (guild_a = ? OR guild_b = ?)",
        (week, guild_id, guild_id)).fetchone()


def war_score(conn, username: str, points: int):
    """Bank war score for the member's lodge. Silent no-op for the
    guildless, bye weeks, or any error — scoring must never break the
    action that earned it."""
    try:
        if points <= 0:
            return
        m = _membership(conn, username)
        if not m:
            return
        week = _week()
        _ensure_war_pairings(conn, week)
        w = _war_of(conn, week, m["guild_id"])
        if not w or w["guild_b"] is None:
            return
        col = "score_a" if w["guild_a"] == m["guild_id"] else "score_b"
        conn.execute(f"UPDATE guild_wars SET {col} = {col} + ? WHERE week_key = ? AND guild_a = ?",
                     (points, week, w["guild_a"]))
        conn.execute("""
            INSERT INTO guild_war_scores (week_key, guild_id, username, score) VALUES (?,?,?,?)
            ON CONFLICT(week_key, guild_id, username) DO UPDATE SET score = score + ?
        """, (week, m["guild_id"], username, points, points))
    except Exception:
        pass


def war_status(conn, username: str) -> dict:
    m = _require_membership(conn, username)
    week = _week()
    _ensure_war_pairings(conn, week)
    w = _war_of(conn, week, m["guild_id"])
    mine = conn.execute("SELECT * FROM guilds WHERE id = ?", (m["guild_id"],)).fetchone()

    def guild_brief(gid):
        g = conn.execute("SELECT * FROM guilds WHERE id = ?", (gid,)).fetchone()
        return {"id": g["id"], "name": g["name"], "renown": g["renown"],
                "banner": json.loads(g["banner_json"]) if g["banner_json"] else None}

    if not w or w["guild_b"] is None:
        return {"in_war": False, "guild": guild_brief(m["guild_id"]),
                "week": week, "ends_in_seconds": _seconds_to_next_monday(),
                "message": "No rival lodge answered the horn this week — the banners rest."}

    we_are_a = w["guild_a"] == m["guild_id"]
    rival_id = w["guild_b"] if we_are_a else w["guild_a"]
    my_score = w["score_a"] if we_are_a else w["score_b"]
    their_score = w["score_b"] if we_are_a else w["score_a"]
    vanguard = [dict(r) for r in conn.execute(
        "SELECT username, score FROM guild_war_scores WHERE week_key = ? AND guild_id = ? ORDER BY score DESC LIMIT 5",
        (week, m["guild_id"])).fetchall()]
    my_row = conn.execute(
        "SELECT score FROM guild_war_scores WHERE week_key = ? AND guild_id = ? AND username = ?",
        (week, m["guild_id"], username)).fetchone()
    return {
        "in_war": True, "week": week,
        "guild": guild_brief(m["guild_id"]), "rival": guild_brief(rival_id),
        "my_score": my_score, "their_score": their_score,
        "my_contribution": my_row["score"] if my_row else 0,
        "vanguard": vanguard,
        "ends_in_seconds": _seconds_to_next_monday(),
        "scoring": {"per_floor": WAR_FLOOR_SCORE, "per_bout": WAR_BOUT_SCORE},
        "spoils": {"win_treasury": WAR_WIN_TREASURY, "win_coin": WAR_WIN_COIN, "lose_coin": WAR_LOSE_COIN},
    }


# ─── Guild Perks ("Boons") — treasury spent on lodge-wide effects ─────
# Design: Guild Perks - Illuminated. Six boons, tier pips, officer+ spends
# the shared treasury. Effects either bite server-side (cap, boss damage,
# shop prices, treasury income) or ride back to the client (hero EXP,
# refit costs) for the local save to apply.

PERKS = {
    "muster":    {"name": "KIN MUSTER",     "max": 5, "base_cost": 400,
                  "desc": "+2 member berths per tier.", "renown_req": 0},
    "coffers":   {"name": "LODGE COFFERS",  "max": 8, "base_cost": 350,
                  "desc": "+10% treasury from every check-in, per tier.", "renown_req": 0},
    "warband":   {"name": "WARBAND",        "max": 6, "base_cost": 450,
                  "desc": "+5% damage to the guild boss, per tier.", "renown_req": 0},
    "quarter":   {"name": "QUARTERMASTER",  "max": 5, "base_cost": 400,
                  "desc": "−4% guild-shop prices, per tier.", "renown_req": 0},
    "mentor":    {"name": "MENTORSHIP",     "max": 5, "base_cost": 300,
                  "desc": "+3% hero EXP for all kin, per tier (applied by your climb).", "renown_req": 25},
    "skywright": {"name": "SKYWRIGHTS",     "max": 4, "base_cost": 500,
                  "desc": "−5% Skydock refit costs, per tier (applied by your fitters).", "renown_req": 100},
}


def _perk_levels(conn, guild_id: int) -> dict:
    rows = conn.execute("SELECT perk_id, level FROM guild_perks WHERE guild_id = ?", (guild_id,)).fetchall()
    return {r["perk_id"]: r["level"] for r in rows}


def _perk_level(conn, guild_id: int, perk_id: str) -> int:
    row = conn.execute("SELECT level FROM guild_perks WHERE guild_id = ? AND perk_id = ?", (guild_id, perk_id)).fetchone()
    return row["level"] if row else 0


def _effective_cap(conn, g) -> int:
    return min(MAX_MEMBER_CAP, g["member_cap"] + 2 * _perk_level(conn, g["id"], "muster"))


def _shop_price(conn, guild_id: int, cost: int) -> int:
    disc = 0.04 * _perk_level(conn, guild_id, "quarter")
    return max(1, int(round(cost * (1 - min(0.5, disc)))))


def perks(conn, username: str) -> dict:
    m = _require_membership(conn, username)
    g = conn.execute("SELECT * FROM guilds WHERE id = ?", (m["guild_id"],)).fetchone()
    levels = _perk_levels(conn, m["guild_id"])
    out = []
    for pid, p in PERKS.items():
        lvl = levels.get(pid, 0)
        locked = g["renown"] < p["renown_req"]
        out.append({
            "id": pid, "name": p["name"], "desc": p["desc"],
            "level": lvl, "max": p["max"],
            "cost": p["base_cost"] * (lvl + 1) if lvl < p["max"] else None,
            "locked": locked, "renown_req": p["renown_req"],
        })
    return {"treasury": g["treasury"], "renown": g["renown"],
            "can_spend": m["rank"] in ("MASTER", "OFFICER"), "perks": out}


def perk_buy(conn, username: str, perk_id: str) -> dict:
    m = _require_membership(conn, username)
    if m["rank"] not in ("MASTER", "OFFICER"):
        raise HTTPException(status_code=403, detail="Only officers spend the lodge's treasury.")
    p = PERKS.get(perk_id)
    if not p:
        raise HTTPException(status_code=404, detail="No such boon.")
    g = conn.execute("SELECT * FROM guilds WHERE id = ?", (m["guild_id"],)).fetchone()
    if g["renown"] < p["renown_req"]:
        raise HTTPException(status_code=400, detail=f"The lodge lacks renown — {p['renown_req']} required.")
    lvl = _perk_level(conn, m["guild_id"], perk_id)
    if lvl >= p["max"]:
        raise HTTPException(status_code=400, detail=f"{p['name']} is already at its final tier.")
    cost = p["base_cost"] * (lvl + 1)
    if g["treasury"] < cost:
        raise HTTPException(status_code=400, detail=f"The treasury holds too little ({cost} needed).")
    conn.execute("UPDATE guilds SET treasury = treasury - ? WHERE id = ?", (cost, m["guild_id"]))
    conn.execute("""
        INSERT INTO guild_perks (guild_id, perk_id, level) VALUES (?,?,1)
        ON CONFLICT(guild_id, perk_id) DO UPDATE SET level = level + 1
    """, (m["guild_id"], perk_id))
    return {"ok": True, "perk_id": perk_id, "level": lvl + 1,
            "message": f"{p['name']} rises to tier {lvl + 1} — the whole lodge feels it."}


# ─── Social: allies (hero loans scrapped by design decision) ─────────

def _pair(a: str, b: str):
    return (a, b) if a < b else (b, a)


def ally_invite(conn, me: str, target: str) -> dict:
    target = (target or "").strip()
    if not target or target == me:
        raise HTTPException(status_code=400, detail="Name an ally who isn't yourself.")
    if not conn.execute("SELECT 1 FROM arena_players WHERE username = ?", (target,)).fetchone():
        raise HTTPException(status_code=404, detail=f"No climber named {target}.")
    row = conn.execute(
        "SELECT * FROM allies WHERE (username_a = ? AND username_b = ?) OR (username_a = ? AND username_b = ?)",
        (me, target, target, me)).fetchone()
    if row:
        if row["status"] == "accepted":
            raise HTTPException(status_code=400, detail="You are already allies.")
        if row["username_a"] == target:
            # they invited us first — accept
            conn.execute("UPDATE allies SET status = 'accepted', since = ? WHERE username_a = ? AND username_b = ?",
                         (time.time(), target, me))
            return {"ok": True, "message": f"{target} had already reached out — you are allies now."}
        raise HTTPException(status_code=400, detail="Your invitation is already on its way.")
    conn.execute("INSERT INTO allies (username_a, username_b, status, since) VALUES (?,?,?,?)",
                 (me, target, "pending", time.time()))
    return {"ok": True, "message": f"Word is sent to {target}."}


def ally_decide(conn, me: str, target: str, accept: bool) -> dict:
    row = conn.execute("SELECT * FROM allies WHERE username_a = ? AND username_b = ? AND status = 'pending'",
                       (target, me)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No such invitation.")
    if accept:
        conn.execute("UPDATE allies SET status = 'accepted', since = ? WHERE username_a = ? AND username_b = ?",
                     (time.time(), target, me))
        return {"ok": True, "message": f"You and {target} climb as allies."}
    conn.execute("DELETE FROM allies WHERE username_a = ? AND username_b = ?", (target, me))
    return {"ok": True, "message": "The invitation is declined."}


def ally_remove(conn, me: str, target: str) -> dict:
    conn.execute(
        "DELETE FROM allies WHERE (username_a = ? AND username_b = ?) OR (username_a = ? AND username_b = ?)",
        (me, target, target, me))
    return {"ok": True, "message": f"{target} is struck from your fellowship."}


def ally_list(conn, me: str) -> dict:
    rows = conn.execute(
        "SELECT * FROM allies WHERE username_a = ? OR username_b = ?", (me, me)).fetchall()
    accepted, incoming, outgoing = [], [], []
    for r in rows:
        other = r["username_b"] if r["username_a"] == me else r["username_a"]
        if r["status"] == "accepted":
            accepted.append(other)
        elif r["username_a"] == me:
            outgoing.append(other)
        else:
            incoming.append(other)
    def enrich(names):
        out = []
        for n in names:
            p = conn.execute(
                "SELECT username, highest_floor, elo, banner_json FROM arena_players WHERE username = ?", (n,)).fetchone()
            g = conn.execute("SELECT g.name FROM guild_members m JOIN guilds g ON g.id = m.guild_id WHERE m.username = ?", (n,)).fetchone()
            out.append({
                "username": n,
                "highest_floor": (p["highest_floor"] if p else 0) or 0,
                "elo": (p["elo"] if p else 1000) or 1000,
                "banner": (json.loads(p["banner_json"]) if p and p["banner_json"] else None),
                "guild": g["name"] if g else None,
            })
        return sorted(out, key=lambda x: -x["highest_floor"])
    return {"allies": enrich(accepted), "incoming": enrich(incoming), "outgoing": enrich(outgoing)}


def _membership(conn, username: str):
    return conn.execute("SELECT * FROM guild_members WHERE username = ?", (username,)).fetchone()


def _require_membership(conn, username: str):
    m = _membership(conn, username)
    if not m:
        raise HTTPException(status_code=400, detail="You are not sworn to any guild.")
    return m


def found_guild(conn, username: str, name: str, motto: str = "", banner: dict = None) -> dict:
    if _membership(conn, username):
        raise HTTPException(status_code=400, detail="You already belong to a guild — leave it first.")
    name = (name or "").strip()[:32]
    if len(name) < 3:
        raise HTTPException(status_code=400, detail="A guild needs a name of at least 3 letters.")
    if conn.execute("SELECT 1 FROM guilds WHERE name = ? COLLATE NOCASE", (name,)).fetchone():
        raise HTTPException(status_code=400, detail="A guild by that name already flies its banner.")
    cur = conn.execute(
        "INSERT INTO guilds (name, motto, banner_json, founder, created_at) VALUES (?,?,?,?,?)",
        (name, (motto or "").strip()[:120], json.dumps(banner or {}), username, time.time()),
    )
    conn.execute(
        "INSERT INTO guild_members (guild_id, username, rank, joined_at, week_key) VALUES (?,?,?,?,?)",
        (cur.lastrowid, username, "MASTER", time.time(), _week()),
    )
    return {"ok": True, "guild_id": cur.lastrowid, "message": f"{name} is founded — its banner rises over the ashfields."}


def registry(conn) -> dict:
    rows = conn.execute("""
        SELECT g.*, COUNT(m.username) AS members FROM guilds g
        LEFT JOIN guild_members m ON m.guild_id = g.id
        GROUP BY g.id ORDER BY g.renown DESC, members DESC LIMIT 50
    """).fetchall()
    return {"guilds": [
        {"id": r["id"], "name": r["name"], "motto": r["motto"], "renown": r["renown"],
         "members": r["members"], "member_cap": r["member_cap"],
         "banner": json.loads(r["banner_json"]) if r["banner_json"] else None}
        for r in rows
    ]}


def apply_to_guild(conn, username: str, guild_id: int, message: str = "") -> dict:
    if _membership(conn, username):
        raise HTTPException(status_code=400, detail="You already belong to a guild.")
    g = conn.execute("SELECT * FROM guilds WHERE id = ?", (guild_id,)).fetchone()
    if not g:
        raise HTTPException(status_code=404, detail="No such guild.")
    pending = conn.execute(
        "SELECT 1 FROM guild_applications WHERE username = ? AND guild_id = ? AND status = 'pending' "
        "AND created_at > ?", (username, guild_id, time.time() - 86400)).fetchone()
    if pending:
        raise HTTPException(status_code=400, detail="One petition per guild per day.")
    conn.execute(
        "INSERT INTO guild_applications (guild_id, username, message, created_at) VALUES (?,?,?,?)",
        (guild_id, username, (message or "").strip()[:200], time.time()),
    )
    return {"ok": True, "message": f"Your petition for kinship reaches {g['name']}."}


def decide_application(conn, username: str, app_id: int, accept: bool) -> dict:
    m = _require_membership(conn, username)
    if m["rank"] not in ("MASTER", "OFFICER"):
        raise HTTPException(status_code=403, detail="Only officers weigh petitions.")
    app = conn.execute("SELECT * FROM guild_applications WHERE id = ? AND status = 'pending'", (app_id,)).fetchone()
    if not app or app["guild_id"] != m["guild_id"]:
        raise HTTPException(status_code=404, detail="No such petition.")
    if not accept:
        conn.execute("UPDATE guild_applications SET status = 'declined' WHERE id = ?", (app_id,))
        return {"ok": True, "message": "The petition is declined."}
    if _membership(conn, app["username"]):
        conn.execute("UPDATE guild_applications SET status = 'stale' WHERE id = ?", (app_id,))
        raise HTTPException(status_code=400, detail="They have since sworn to another guild.")
    g = conn.execute("SELECT * FROM guilds WHERE id = ?", (m["guild_id"],)).fetchone()
    count = conn.execute("SELECT COUNT(*) AS c FROM guild_members WHERE guild_id = ?", (m["guild_id"],)).fetchone()["c"]
    cap = _effective_cap(conn, g)   # Kin Muster widens the hall
    if count >= cap:
        raise HTTPException(status_code=400, detail=f"The hall is full ({count}/{cap}).")
    conn.execute("UPDATE guild_applications SET status = 'accepted' WHERE id = ?", (app_id,))
    conn.execute(
        "INSERT INTO guild_members (guild_id, username, rank, joined_at, week_key) VALUES (?,?,?,?,?)",
        (m["guild_id"], app["username"], "MEMBER", time.time(), _week()),
    )
    return {"ok": True, "message": f"{app['username']} joins the guild."}


def leave_guild(conn, username: str) -> dict:
    m = _require_membership(conn, username)
    if m["rank"] == "MASTER":
        others = conn.execute(
            "SELECT username FROM guild_members WHERE guild_id = ? AND username != ? "
            "ORDER BY CASE rank WHEN 'OFFICER' THEN 0 ELSE 1 END, joined_at ASC LIMIT 1",
            (m["guild_id"], username)).fetchone()
        if others:
            conn.execute("UPDATE guild_members SET rank = 'MASTER' WHERE username = ?", (others["username"],))
        else:
            conn.execute("DELETE FROM guilds WHERE id = ?", (m["guild_id"],))
    conn.execute("DELETE FROM guild_members WHERE username = ?", (username,))
    return {"ok": True, "message": "You walk out from under the banner."}


def _boss_today(conn, guild_id: int):
    today = _today()
    row = conn.execute("SELECT * FROM guild_boss WHERE guild_id = ? AND date = ?", (guild_id, today)).fetchone()
    if not row:
        name, hp_per_member = random.Random(f"{guild_id}:{today}").choice(BOSSES)
        members = conn.execute(
            "SELECT COUNT(*) AS c FROM guild_members WHERE guild_id = ?", (guild_id,)).fetchone()["c"]
        hp = hp_per_member * max(1, members)
        conn.execute(
            "INSERT OR IGNORE INTO guild_boss (guild_id, date, boss_name, max_hp, hp) VALUES (?,?,?,?,?)",
            (guild_id, today, name, hp, hp))
        row = conn.execute("SELECT * FROM guild_boss WHERE guild_id = ? AND date = ?", (guild_id, today)).fetchone()
    return row


def my_guild(conn, username: str) -> dict:
    m = _membership(conn, username)
    if not m:
        return {"in_guild": False}
    g = conn.execute("SELECT * FROM guilds WHERE id = ?", (m["guild_id"],)).fetchone()
    members = conn.execute("""
        SELECT gm.username, gm.rank, gm.joined_at, gm.weekly_pledge, p.highest_floor, p.elo
        FROM guild_members gm LEFT JOIN arena_players p ON p.username = gm.username
        WHERE gm.guild_id = ?
        ORDER BY CASE gm.rank WHEN 'MASTER' THEN 0 WHEN 'OFFICER' THEN 1 ELSE 2 END, gm.joined_at ASC
    """, (m["guild_id"],)).fetchall()
    boss = _boss_today(conn, m["guild_id"])
    today = _today()
    my_strikes = conn.execute(
        "SELECT strikes, damage FROM guild_boss_strikes WHERE guild_id = ? AND date = ? AND username = ?",
        (m["guild_id"], today, username)).fetchone()
    tribute = conn.execute(
        "SELECT username, damage FROM guild_boss_strikes WHERE guild_id = ? AND date = ? ORDER BY damage DESC LIMIT 10",
        (m["guild_id"], today)).fetchall()
    week = _week()
    pledge = conn.execute(
        "SELECT COALESCE(SUM(weekly_pledge), 0) AS total FROM guild_members WHERE guild_id = ? AND week_key = ?",
        (m["guild_id"], week)).fetchone()["total"]
    apps = []
    if m["rank"] in ("MASTER", "OFFICER"):
        apps = [dict(r) for r in conn.execute(
            "SELECT id, username, message, created_at FROM guild_applications WHERE guild_id = ? AND status = 'pending' ORDER BY id",
            (m["guild_id"],)).fetchall()]
    perk_levels = _perk_levels(conn, m["guild_id"])
    return {
        "in_guild": True,
        "guild": {"id": g["id"], "name": g["name"], "motto": g["motto"], "renown": g["renown"],
                  "treasury": g["treasury"], "member_cap": _effective_cap(conn, g),
                  "banner": json.loads(g["banner_json"]) if g["banner_json"] else None},
        # Client-applied boons — the local save consumes these multipliers.
        "perks": perk_levels,
        "boons": {
            "hero_exp_pct": 3 * perk_levels.get("mentor", 0),
            "refit_discount_pct": 5 * perk_levels.get("skywright", 0),
        },
        "members": [
            {"username": r["username"], "rank": r["rank"], "highest_floor": r["highest_floor"] or 0,
             "elo": r["elo"] or 1000, "weekly_pledge": r["weekly_pledge"], "you": r["username"] == username}
            for r in members
        ],
        "me": {"rank": m["rank"], "guild_coin": m["guild_coin"], "checked_in": m["last_checkin"] == today},
        "boss": {
            "name": boss["boss_name"], "hp": boss["hp"], "max_hp": boss["max_hp"], "killed": bool(boss["killed"]),
            "my_strikes": my_strikes["strikes"] if my_strikes else 0, "strikes_per_day": BOSS_STRIKES_PER_DAY,
            "resets_in_seconds": _seconds_to_utc_midnight(),
            "tribute": [{"username": t["username"], "damage": t["damage"]} for t in tribute],
        },
        "pledge": {"floors": pledge, "week": week},
        "applications": apps,
    }


def checkin(conn, username: str) -> dict:
    m = _require_membership(conn, username)
    today = _today()
    if m["last_checkin"] == today:
        raise HTTPException(status_code=400, detail="You've already signed the hall's ledger today.")
    week = _week()
    p = conn.execute("SELECT highest_floor FROM arena_players WHERE username = ?", (username,)).fetchone()
    pledge_add = max(1, (p["highest_floor"] or 0) // 10)
    conn.execute(
        "UPDATE guild_members SET last_checkin = ?, guild_coin = guild_coin + ?, "
        "weekly_pledge = CASE WHEN week_key = ? THEN weekly_pledge + ? ELSE ? END, week_key = ? WHERE username = ?",
        (today, CHECKIN_COIN, week, pledge_add, pledge_add, week, username))
    # Lodge Coffers deepens every check-in's treasury tithe.
    treasury_add = int(round(CHECKIN_TREASURY * (1 + 0.10 * _perk_level(conn, m["guild_id"], "coffers"))))
    conn.execute("UPDATE guilds SET treasury = treasury + ?, renown = renown + 1 WHERE id = ?", (treasury_add, m["guild_id"]))
    return {"ok": True, "coin": CHECKIN_COIN, "pledge": pledge_add,
            "message": f"Signed in — +{CHECKIN_COIN} guild coin, {pledge_add} floors pledged."}


BOSS_UNIT_ID = -777


def _boss_unit(boss_row, guild_id: int) -> dict:
    """The daily boss as a combat-sim opponent (same hero-dict shape
    resolve_arena_fight expects). Stats are seeded per guild+date so every
    member fights the same beast all day; HP in the sim is the guild bar's
    REMAINING hp — the fight ends when the party is spent or the round cap
    hits, and the damage they landed is what gets banked."""
    rng = random.Random(f"boss:{guild_id}:{boss_row['date']}")
    tier = rng.uniform(0.9, 1.2)
    return {
        "id": BOSS_UNIT_ID, "name": boss_row["boss_name"], "level": 60,
        "health": boss_row["hp"], "max_health": boss_row["hp"],
        "strength": int(220 * tier), "intelligence": int(160 * tier),
        "agility": int(90 * tier), "endurance": int(180 * tier),
        "defense": int(180 * tier), "willpower": 80, "luck": 20,
        "morale": 100, "stress": 0,
        "power_stat": "strength", "hero_class": "Boss",
        "_skills": [], "_traits": [],
    }


def strike_boss(conn, username: str) -> dict:
    """A strike is a REAL fight: the member's submitted arena team runs the
    combat sim against the beast (snapshot teams, arena rules — nobody
    truly dies). Damage landed on the boss is banked against the shared
    daily HP bar; the full combat result rides back for the client's
    battle animation."""
    from combat import resolve_arena_fight

    m = _require_membership(conn, username)
    today = _today()
    boss = _boss_today(conn, m["guild_id"])
    if boss["killed"]:
        raise HTTPException(status_code=400, detail="The beast is already down — it rises again at dawn.")
    row = conn.execute(
        "SELECT strikes FROM guild_boss_strikes WHERE guild_id = ? AND date = ? AND username = ?",
        (m["guild_id"], today, username)).fetchone()
    if row and row["strikes"] >= BOSS_STRIKES_PER_DAY:
        raise HTTPException(status_code=400, detail=f"Your {BOSS_STRIKES_PER_DAY} strikes are spent — dawn restores them.")
    p = conn.execute("SELECT team_json FROM arena_players WHERE username = ?", (username,)).fetchone()
    if not p or not p["team_json"]:
        raise HTTPException(status_code=400, detail="Submit a team from the Arena screen first — the hunt needs hunters.")
    team = json.loads(p["team_json"])

    fight = resolve_arena_fight(team, [_boss_unit(boss, m["guild_id"])])
    damage = sum(t.get("damage", 0) for t in fight.get("turns", [])
                 if t.get("target_id") == BOSS_UNIT_ID and t.get("damage"))
    # Warband sharpens every strike against the beast.
    damage = int(damage * (1 + 0.05 * _perk_level(conn, m["guild_id"], "warband")))
    damage = max(1, int(damage))
    conn.execute("""
        INSERT INTO guild_boss_strikes (guild_id, date, username, strikes, damage) VALUES (?,?,?,1,?)
        ON CONFLICT(guild_id, date, username) DO UPDATE SET strikes = strikes + 1, damage = damage + ?
    """, (m["guild_id"], today, username, damage, damage))
    new_hp = max(0, boss["hp"] - damage)
    conn.execute("UPDATE guild_boss SET hp = ? WHERE guild_id = ? AND date = ?", (new_hp, m["guild_id"], today))

    result = {"ok": True, "damage": damage, "hp": new_hp, "max_hp": boss["max_hp"], "killed": False}
    if new_hp <= 0:
        conn.execute("UPDATE guild_boss SET killed = 1 WHERE guild_id = ? AND date = ?", (m["guild_id"], today))
        conn.execute("UPDATE guild_members SET guild_coin = guild_coin + ? WHERE guild_id = ?", (BOSS_KILL_COIN, m["guild_id"]))
        top = conn.execute(
            "SELECT username FROM guild_boss_strikes WHERE guild_id = ? AND date = ? ORDER BY damage DESC LIMIT 1",
            (m["guild_id"], today)).fetchone()
        if top:
            conn.execute("UPDATE guild_members SET guild_coin = guild_coin + ? WHERE username = ?", (BOSS_TOP_BONUS_COIN, top["username"]))
        conn.execute("UPDATE guilds SET renown = renown + 25 WHERE id = ?", (m["guild_id"],))
        result["killed"] = True
        result["message"] = f"{boss['boss_name']} falls! +{BOSS_KILL_COIN} guild coin for every member; the top blade takes +{BOSS_TOP_BONUS_COIN}."
    else:
        result["message"] = f"Your strike lands for {damage:,}."
    # ride the full sim back for the client's battle animation (CombatArena)
    result["combat"] = {
        "winner": fight.get("winner"),
        "initial_state": fight.get("initial_state"),
        "turns": fight.get("turns"),
        "rounds": fight.get("rounds"),
        "log": fight.get("log", [])[-20:],
    }
    return result


def shop(conn, username: str) -> dict:
    m = _require_membership(conn, username)
    week = _week()
    bought = {r["item_id"]: r["count"] for r in conn.execute(
        "SELECT item_id, count FROM guild_shop_purchases WHERE week_key = ? AND username = ?", (week, username)).fetchall()}
    return {
        "guild_coin": m["guild_coin"],
        # Quartermaster haggles every price down.
        "items": [
            {"id": iid, "name": it["name"], "desc": it["desc"],
             "cost": _shop_price(conn, m["guild_id"], it["cost"]), "base_cost": it["cost"],
             "weekly": it["weekly"], "bought": bought.get(iid, 0)}
            for iid, it in SHOP_ITEMS.items()
        ],
    }


def shop_buy(conn, username: str, item_id: str) -> dict:
    m = _require_membership(conn, username)
    it = SHOP_ITEMS.get(item_id)
    if not it:
        raise HTTPException(status_code=404, detail="The shop stocks no such thing.")
    week = _week()
    row = conn.execute(
        "SELECT count FROM guild_shop_purchases WHERE week_key = ? AND username = ? AND item_id = ?",
        (week, username, item_id)).fetchone()
    if row and row["count"] >= it["weekly"]:
        raise HTTPException(status_code=400, detail="Sold out for you this week — restocks Monday.")
    cost = _shop_price(conn, m["guild_id"], it["cost"])
    if m["guild_coin"] < cost:
        raise HTTPException(status_code=400, detail=f"Not enough guild coin ({cost} needed).")
    conn.execute("UPDATE guild_members SET guild_coin = guild_coin - ? WHERE username = ?", (cost, username))
    conn.execute("""
        INSERT INTO guild_shop_purchases (week_key, username, item_id, count) VALUES (?,?,?,1)
        ON CONFLICT(week_key, username, item_id) DO UPDATE SET count = count + 1
    """, (week, username, item_id))
    # The client applies the grant to its own save (local mail with rewards).
    return {"ok": True, "grant": it["grant"], "name": it["name"],
            "message": f"{it['name']} — bought. The quartermaster hands it over."}
