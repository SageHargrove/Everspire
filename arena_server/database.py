"""
Arena server's own SQLite store — completely separate from any player's
local save file. Nothing here ever touches backend/saves/*.db; a player's
real heroes/profile are never read or written by this service. Arena
fights are resolved against snapshots the client submits, not live saves.
"""
import sqlite3
import os
from contextlib import contextmanager

# ARENA_DB_PATH lets deployments (the Dockerfile mounts /app/data as a
# volume) put the database somewhere that survives image rebuilds; local
# runs keep the old alongside-the-code default.
DB_PATH = os.environ.get("ARENA_DB_PATH") or os.path.join(os.path.dirname(__file__), "arena.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS arena_players (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            token TEXT,
            token_expiry REAL,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            team_json TEXT,
            highest_floor INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS arena_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player1 TEXT NOT NULL,
            player2 TEXT NOT NULL,
            winner TEXT,
            log_json TEXT,
            timestamp REAL NOT NULL
        );

        -- Login audit trail (time/IP), surfaced to the player via
        -- /auth/logins so an unfamiliar sign-in is visible to them.
        CREATE TABLE IF NOT EXISTS login_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            ip TEXT,
            at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_login_audit_user ON login_audit(username, id DESC);

        -- One paid hire per (hirer, listing) FOREVER. Without this the
        -- training market minted unlimited gems: every repeat hire paid the
        -- lister again while charging the hirer nothing server-side.
        CREATE TABLE IF NOT EXISTS market_hires (
            listing_id INTEGER NOT NULL,
            hirer TEXT NOT NULL,
            at REAL NOT NULL,
            PRIMARY KEY (listing_id, hirer)
        );
        
        CREATE TABLE IF NOT EXISTS arena_season_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            season_end_date REAL NOT NULL,
            reward_type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            claimed INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS training_market (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            hero_name TEXT NOT NULL,
            hero_class TEXT NOT NULL,
            hero_stats_json TEXT NOT NULL,
            hero_skills_json TEXT NOT NULL,
            gem_cost INTEGER NOT NULL,
            listed_at REAL NOT NULL
        );

        -- ─── Raids (PvP base sieges) ──────────────────────────────
        -- One row per resolved siege. capture_candidates_json holds the
        -- losing side's roster snapshot; the victor gets one claim
        -- (prisoner_json) — see /arena/raid/claim_prisoner.
        CREATE TABLE IF NOT EXISTS raids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attacker TEXT NOT NULL,
            defender TEXT NOT NULL,
            winner TEXT NOT NULL,
            spoils_json TEXT,
            capture_candidates_json TEXT,
            prisoner_json TEXT,
            prisoner_claimed INTEGER DEFAULT 0,
            log_json TEXT,
            timestamp REAL NOT NULL
        );

        -- Per-player raid inbox: the other side of a siege learns what
        -- happened to them (resources lost, hero captured) the next time
        -- their client polls /arena/raid/events and applies it locally.
        CREATE TABLE IF NOT EXISTS raid_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            seen INTEGER DEFAULT 0,
            created_at REAL NOT NULL
        );

        -- ─── Server-wide tournaments ──────────────────────────────
        CREATE TABLE IF NOT EXISTS tournament_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            format TEXT NOT NULL,
            username TEXT NOT NULL,
            team_json TEXT NOT NULL,
            points INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            placement INTEGER,
            paid_out INTEGER DEFAULT 0,
            registered_at REAL NOT NULL,
            UNIQUE(week_key, format, username)
        );

        CREATE TABLE IF NOT EXISTS tournament_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            format TEXT NOT NULL,
            round INTEGER NOT NULL,
            player1 TEXT NOT NULL,
            player2 TEXT,
            winner TEXT,
            log_json TEXT,
            timestamp REAL NOT NULL
        );

        -- Tracks which (week, format) brackets have already been resolved /
        -- paid so lazy resolution stays idempotent.
        CREATE TABLE IF NOT EXISTS tournament_state (
            week_key TEXT NOT NULL,
            format TEXT NOT NULL,
            resolved INTEGER DEFAULT 0,
            paid_out INTEGER DEFAULT 0,
            resolved_at REAL,
            PRIMARY KEY (week_key, format)
        );
    """)

    # Attempt to add highest_floor column if it doesn't exist (for existing DBs)
    try:
        conn.execute("ALTER TABLE arena_players ADD COLUMN highest_floor INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass # Column already exists

    try:
        conn.execute("ALTER TABLE arena_players ADD COLUMN email TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_players_email ON arena_players(email)")
    except sqlite3.OperationalError:
        pass # Column already exists

    try:
        conn.execute("ALTER TABLE arena_players ADD COLUMN elo INTEGER DEFAULT 1000")
    except sqlite3.OperationalError:
        pass # Column already exists

    # Raid opt-in + world-map placement + the defense snapshot the client
    # submits (base defense ratings, defending team, lootable resources).
    for col, ddl in (
        ("is_raider", "INTEGER DEFAULT 0"),
        ("coord_x", "INTEGER"),
        ("coord_y", "INTEGER"),
        ("defense_json", "TEXT"),
        ("defense_updated_at", "REAL"),
        ("last_raided_at", "REAL"),   # raid shield: recently-hit bases can't be immediately re-hit
        ("raid_wins", "INTEGER DEFAULT 0"),
        ("raid_losses", "INTEGER DEFAULT 0"),
        ("defense_wins", "INTEGER DEFAULT 0"),
        ("defense_losses", "INTEGER DEFAULT 0"),
        # The player's standard (cloth/cut/frame/sigil/emblem JSON from the
        # local Banner Studio) — carried so opponents see your banner on
        # leaderboards and the raid map.
        ("banner_json", "TEXT"),
    ):
        try:
            conn.execute(f"ALTER TABLE arena_players ADD COLUMN {col} {ddl}")
        except sqlite3.OperationalError:
            pass # Column already exists
    conn.commit()
    conn.close()
    print("[Arena] Database initialized.")
