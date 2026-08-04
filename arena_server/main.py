"""
Arena server — a small, separate FastAPI app from the main game backend.
Hosts PvP challenges between players using client-submitted, already-fully-
resolved hero stat snapshots. Never touches any player's local save file;
this process owns nothing but arena.db (player accounts/tokens + match
history). See arena_server/database.py and combat.py for why.
"""
import os
import random
import secrets
import time
import json

import bcrypt
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from security import (
    BodySizeLimitMiddleware, SecurityHeadersMiddleware,
    client_ip, rate_limit, hash_token, clamp_team,
)

from database import db, init_db
from combat import resolve_arena_fight
from elo import update_elo
from models import (
    WORLD_SIZE, DEFAULT_SCOUT_RADIUS, MAX_SCOUT_RADIUS, MAX_DEFENSE_JSON_BYTES,
    RaidOptInRequest, SubmitDefenseRequest, ScoutRequest, RaidAttackRequest,
    ClaimPrisonerRequest, TOURNAMENT_FORMATS, TournamentRegisterRequest,
    BannerRequest,
)
from raids import resolve_siege, build_scout_report
import tournaments
import guilds
import chat

TOKEN_LIFETIME_SECONDS = 7 * 24 * 60 * 60  # 7 days

import re

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
MAX_TEAM_SIZE = 5
MAX_TEAM_JSON_BYTES = 64 * 1024   # a legit 5-hero snapshot is a few KB
MAX_MARKET_JSON_BYTES = 16 * 1024
MAX_GEM_COST = 1000               # limits the cross-account gem-inbox exploit blast radius
MAX_REPORTED_FLOOR = 1000

# Admin actions require ARENA_ADMIN_KEY in the server's environment — the
# old hardcoded "secret_admin_key_123" meant anyone reading the public repo
# could wipe every player's season.
ADMIN_KEY = os.environ.get("ARENA_ADMIN_KEY")

# Per-account failure counter. Deliberately NOT a hard lockout: locking a
# username out on failures alone let anyone freeze a known player's account
# indefinitely (5 bad guesses/minute, forever). Instead failures add delay
# and the real brute-force ceiling is the per-IP limiter below.
_login_failures: dict[str, list] = {}  # key -> [fail_count, last_fail_ts]
LOGIN_FAIL_WINDOW = 15 * 60
LOGIN_FAIL_SOFT_LIMIT = 10        # per-account failures in the window before extra friction

# Per-IP throttles (sliding windows, see security.rate_limit).
RL_AUTH = (20, 15 * 60)           # register/login attempts per IP / 15 min
RL_FIGHT = (30, 10 * 60)          # combat-running endpoints: each runs a full sim
RL_MARKET = (20, 10 * 60)         # market listing/hiring
RL_WRITE = (120, 60)              # general authenticated writes
RL_RAID = (30, 10 * 60)

app = FastAPI(title="Giltgrave — Arena Server")

# Order matters: body cap runs OUTERMOST so oversized requests die before
# anything buffers them.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(BodySizeLimitMiddleware, max_bytes=256 * 1024)

# The game client is a desktop app (no browser Origin) and auth is a Bearer
# header, not a cookie — so no site needs cross-origin credentialed access
# here. Keeping this closed means a random web page can't quietly script the
# API against a logged-in player's token.
_ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ARENA_ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


def _throttle(request: Request, bucket: str, spec: tuple[int, int], subject: str | None = None):
    """Rate-limit one request. Keyed by real client IP (Caddy-aware), and
    additionally by account where that's the thing being protected."""
    key = f"{bucket}:{subject or client_ip(request)}"
    allowed, retry = rate_limit(key, spec[0], spec[1])
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests — slow down and retry in {retry}s",
            headers={"Retry-After": str(retry)},
        )


@app.on_event("startup")
def _startup():
    init_db()
    with db() as conn:
        guilds.init_tables(conn)
        chat.init_tables(conn)


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthRegisterRequest(BaseModel):
    email: str
    username: str          # public display name / world identity
    password: str


class AuthLoginRequest(BaseModel):
    identifier: str        # email OR username
    password: str


class SubmitTeamRequest(BaseModel):
    team: list[dict]


class ChallengeRequest(BaseModel):
    opponent: str


class UpdateFloorRequest(BaseModel):
    highest_floor: int


def _require_player(authorization: str | None) -> str:
    """Validates the Bearer token from the Authorization header, returns
    the owning username. Raises 401 on anything wrong.

    Tokens are stored HASHED (see security.hash_token) so a copy of arena.db
    no longer yields usable sessions. Legacy plaintext rows are still
    accepted once and upgraded in place, so deploying this doesn't sign
    every logged-in player out."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    hashed = hash_token(token)
    with db() as conn:
        row = conn.execute(
            "SELECT username, token_expiry FROM arena_players WHERE token = ?", (hashed,)
        ).fetchone()
        if not row:
            # Legacy plaintext rows only. The NOT LIKE guard is essential:
            # without it, someone holding a stolen DB could paste a stored
            # digest straight back as a bearer token and be authenticated.
            legacy = conn.execute(
                "SELECT username, token_expiry FROM arena_players "
                "WHERE token = ? AND token NOT LIKE 'v2:%'", (token,)
            ).fetchone()
            if legacy:
                conn.execute(
                    "UPDATE arena_players SET token = ? WHERE username = ?",
                    (hashed, legacy["username"]),
                )
                row = legacy
    if not row:
        raise HTTPException(status_code=401, detail="Invalid token")
    if row["token_expiry"] is None or row["token_expiry"] < time.time():
        raise HTTPException(status_code=401, detail="Token expired, please log in again")
    return row["username"]


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# A real bcrypt hash of a random string, compared against when the account
# doesn't exist so a miss costs the same time as a wrong password (no
# timing-based username enumeration).
_DUMMY_BCRYPT = bcrypt.hashpw(secrets.token_hex(16).encode(), bcrypt.gensalt()).decode()


def _record_login(conn, username: str, ip: str) -> None:
    """Append to the login audit trail (surfaced via /auth/logins) and prune
    to the last 20 per account. A player seeing an unfamiliar IP is the
    cheapest account-compromise detector available."""
    try:
        conn.execute(
            "INSERT INTO login_audit (username, ip, at) VALUES (?, ?, ?)",
            (username, ip[:64], time.time()),
        )
        conn.execute(
            """DELETE FROM login_audit WHERE username = ? AND id NOT IN
               (SELECT id FROM login_audit WHERE username = ? ORDER BY id DESC LIMIT 20)""",
            (username, username),
        )
    except Exception:
        pass  # auditing must never block a legitimate login


def _issue_token(conn, username: str) -> str:
    """Mint a session token. The plaintext is returned to the caller exactly
    once; only its hash is persisted."""
    token = secrets.token_hex(32)
    conn.execute(
        "UPDATE arena_players SET token = ?, token_expiry = ? WHERE username = ?",
        (hash_token(token), time.time() + TOKEN_LIFETIME_SECONDS, username),
    )
    return token


LANDING_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "landing", "index.html")
# Where "Download" sends people.
#
# /releases/latest/download/<asset> resolves to that exact asset on the newest
# release, so clicking Download starts the installer downloading immediately —
# no GitHub page, no picking a file out of a list. The asset name is the
# contract: tools/make_release.py must keep producing Giltgrave-Setup.exe.
#
# Until the first release exists this 404s, so /download checks and falls back
# to the releases page rather than dead-ending the button.
SETUP_ASSET = "Giltgrave-Setup.exe"
# The landing page's edition chooser offers a build that ships with the local
# image-generation pipeline preinstalled. Until that asset exists on a release,
# /download?edition=gpu falls back to the standard installer (generation can
# always be enabled in-game afterwards), so the button never dead-ends.
SETUP_ASSET_GPU = "Giltgrave-Setup-GPU.exe"
RELEASES_BASE = "https://github.com/SageHargrove/Everspire/releases"
DOWNLOAD_URL = f"{RELEASES_BASE}/latest/download/{SETUP_ASSET}"
RELEASES_URL = RELEASES_BASE

# Fonts, key art, and screenshots for the landing page. Same no-CDN rule as
# the page itself: everything it references is served from this container.
LANDING_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "landing", "assets")
if os.path.isdir(LANDING_ASSETS):
    from fastapi.staticfiles import StaticFiles
    app.mount("/landing/assets", StaticFiles(directory=LANDING_ASSETS), name="landing-assets")


@app.get("/", response_class=HTMLResponse)
def root_landing():
    """The public landing page. Eventually playeverspire.com points here.

    Safe to serve from the API root: NOTHING in the game client requests the
    bare root — every call is under /auth or /arena (checked before writing
    this). The previous handler was an explicitly "human-friendly" JSON stub
    for exactly this situation, so this replaces a placeholder rather than an
    endpoint. The old JSON still lives at /status for uptime checks.

    Serving it here rather than via Caddy is deliberate: no vhost, no second
    TLS cert, no reverse-proxy rule that could shadow an API route, and it
    ships through the existing redeploy_world_server.sh."""
    try:
        with open(LANDING_HTML, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except OSError:
        # Never let a missing asset take the root down.
        return HTMLResponse(
            "<h1>Giltgrave</h1><p>Multiplayer world server is running. "
            f'<a href="{DOWNLOAD_URL}">Download the game</a></p>')


_DL_CACHE: dict = {}


def _asset_exists(asset: str) -> bool:
    """HEAD-probe a latest-release asset, cached 5 minutes per asset so
    clicking Download doesn't hit GitHub every time."""
    now = time.time()
    hit = _DL_CACHE.get(asset)
    if hit is None or now - hit[1] > 300:
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{RELEASES_BASE}/latest/download/{asset}", method="HEAD")
            with urllib.request.urlopen(req, timeout=5) as r:
                ok = r.status < 400
        except Exception:
            ok = False
        hit = (ok, now)
        _DL_CACHE[asset] = hit
    return hit[0]


@app.get("/download")
def download_redirect(edition: str = ""):
    """One stable link for the landing page's buttons, so publishing a new
    release needs no edit here and no redeploy of this server.

    ?edition=gpu asks for the generation-bundled installer; if that asset
    isn't published (yet) it degrades to the standard installer, and if no
    release exists at all it lands on the releases page — a button that
    downloads nothing is worse than one that explains itself."""
    candidates = [SETUP_ASSET_GPU, SETUP_ASSET] if edition == "gpu" else [SETUP_ASSET]
    for asset in candidates:
        if _asset_exists(asset):
            return RedirectResponse(
                f"{RELEASES_BASE}/latest/download/{asset}", status_code=302)
    return RedirectResponse(RELEASES_URL, status_code=302)


@app.get("/status")
def root_status():
    """The machine-readable root that used to live at /. Kept so uptime checks
    and anything scripted against it keep working."""
    return {"service": "Giltgrave — World Server", "status": "ok",
            "hint": "This is the multiplayer API. Launch the game to play."}


@app.post("/auth/register")
def auth_register(req: AuthRegisterRequest, request: Request):
    """Account creation for the startup login screen: email + display name +
    password. Issues a session token immediately (register == logged in).

    Throttled per IP: free unlimited account creation was the force
    multiplier behind the training-market payout exploit (mint accounts,
    farm cross-account rewards)."""
    _throttle(request, "auth", RL_AUTH)
    email = req.email.strip().lower()
    username = req.username.strip()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    if not USERNAME_RE.match(username):
        raise HTTPException(status_code=400, detail="Display name must be 3-20 characters: letters, digits, underscore")
    if len(req.password) < 6 or len(req.password) > 128:
        raise HTTPException(status_code=400, detail="Password must be 6-128 characters")
    password_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    with db() as conn:
        if conn.execute("SELECT 1 FROM arena_players WHERE username = ?", (username,)).fetchone():
            raise HTTPException(status_code=409, detail="Display name already taken")
        if conn.execute("SELECT 1 FROM arena_players WHERE email = ?", (email,)).fetchone():
            raise HTTPException(status_code=409, detail="An account with that email already exists")
        conn.execute(
            "INSERT INTO arena_players (username, email, password_hash) VALUES (?, ?, ?)",
            (username, email, password_hash),
        )
        token = _issue_token(conn, username)
    return {"token": token, "username": username, "email": email}


@app.post("/auth/login")
def auth_login(req: AuthLoginRequest, request: Request):
    """Login by email or display name.

    Brute-force ceiling is the per-IP limiter (RL_AUTH). Per-account
    failures add friction but never hard-lock — the previous 60s username
    lockout meant anyone could keep a known player permanently locked out
    just by failing five logins a minute against their name."""
    _throttle(request, "auth", RL_AUTH)
    ident = req.identifier.strip()
    key = ident.lower()
    ip = client_ip(request)

    # Per-account soft throttle: many recent failures against this one
    # account also costs the attacker a tighter IP budget.
    entry = _login_failures.get(key)
    now = time.time()
    if entry and now - entry[1] > LOGIN_FAIL_WINDOW:
        entry = None
    if entry and entry[0] >= LOGIN_FAIL_SOFT_LIMIT:
        _throttle(request, "auth_hot", (5, LOGIN_FAIL_WINDOW))

    with db() as conn:
        row = conn.execute(
            "SELECT username, email, password_hash FROM arena_players WHERE email = ? OR username = ?",
            (key, ident),
        ).fetchone()
        # Constant-ish work whether or not the account exists, so response
        # timing doesn't cleanly enumerate valid usernames/emails.
        stored = row["password_hash"] if row else _DUMMY_BCRYPT
        ok = bcrypt.checkpw(req.password.encode(), stored.encode())
        if not row or not ok:
            prior = (_login_failures.get(key) or [0, 0])[0]
            _login_failures[key] = [prior + 1, now]
            raise HTTPException(status_code=401, detail="Invalid credentials")
        _login_failures.pop(key, None)
        token = _issue_token(conn, row["username"])
        _record_login(conn, row["username"], ip)
    return {"token": token, "username": row["username"], "email": row["email"]}


@app.get("/auth/me")
def auth_me(authorization: str | None = Header(default=None)):
    """Session check for the startup screen: valid token -> identity."""
    username = _require_player(authorization)
    with db() as conn:
        row = conn.execute(
            "SELECT username, email, wins, losses, highest_floor FROM arena_players WHERE username = ?",
            (username,),
        ).fetchone()
    return dict(row)


@app.post("/auth/discord")
def auth_discord():
    """OAuth scaffold, same deal as Google: becomes live when
    DISCORD_CLIENT_ID is configured (system-browser OAuth -> code exchange ->
    upsert account by Discord email, issue session token)."""
    if not os.environ.get("DISCORD_CLIENT_ID"):
        raise HTTPException(status_code=501, detail="Discord sign-in is not configured on this server yet")
    raise HTTPException(status_code=501, detail="Discord sign-in verification not implemented yet")


@app.post("/auth/google")
def auth_google():
    """OAuth scaffold: becomes live when GOOGLE_CLIENT_ID is configured on
    the server (verify the posted id_token against Google's certs, upsert an
    account keyed by email, issue a session token). Deliberately 501 until
    then so the client can show the button as 'coming soon'."""
    if not os.environ.get("GOOGLE_CLIENT_ID"):
        raise HTTPException(status_code=501, detail="Google sign-in is not configured on this server yet")
    raise HTTPException(status_code=501, detail="Google sign-in verification not implemented yet")


@app.post("/arena/register")
def register(req: RegisterRequest, request: Request):
    """Legacy username+password registration (pre-dates /auth/register).
    Same per-IP throttle — unlimited free accounts is what makes every
    cross-account economy exploit scalable."""
    _throttle(request, "auth", RL_AUTH)
    username = req.username.strip()
    if not username or not req.password:
        raise HTTPException(status_code=400, detail="Username and password are required")
    if not USERNAME_RE.match(username):
        raise HTTPException(status_code=400, detail="Username must be 3-20 characters: letters, digits, underscore")
    if len(req.password) < 6 or len(req.password) > 128:
        raise HTTPException(status_code=400, detail="Password must be 6-128 characters")
    password_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    with db() as conn:
        existing = conn.execute(
            "SELECT username FROM arena_players WHERE username = ?", (username,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Username already taken")
        conn.execute(
            "INSERT INTO arena_players (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
    return {"status": "registered", "username": username}


@app.post("/arena/login")
def login(req: LoginRequest, request: Request):
    """Legacy username-only login. Shares the hardened path: per-IP throttle,
    constant-time miss, token hashed at rest, audit trail. (It previously
    minted a PLAINTEXT token inline, bypassing _issue_token entirely.)"""
    _throttle(request, "auth", RL_AUTH)
    uname = req.username.strip()
    key = uname.lower()
    ip = client_ip(request)
    now = time.time()

    entry = _login_failures.get(key)
    if entry and now - entry[1] > LOGIN_FAIL_WINDOW:
        entry = None
    if entry and entry[0] >= LOGIN_FAIL_SOFT_LIMIT:
        _throttle(request, "auth_hot", (5, LOGIN_FAIL_WINDOW))

    with db() as conn:
        row = conn.execute(
            "SELECT username, password_hash FROM arena_players WHERE username = ?",
            (uname,),
        ).fetchone()
        stored = row["password_hash"] if row else _DUMMY_BCRYPT
        ok = bcrypt.checkpw(req.password.encode(), stored.encode())
        if not row or not ok:
            prior = (_login_failures.get(key) or [0, 0])[0]
            _login_failures[key] = [prior + 1, now]
            raise HTTPException(status_code=401, detail="Invalid username or password")
        _login_failures.pop(key, None)
        token = _issue_token(conn, row["username"])
        _record_login(conn, row["username"], ip)
    return {"token": token, "username": row["username"]}


@app.get("/auth/logins")
def auth_logins(authorization: str | None = Header(default=None)):
    """The caller's own recent sign-ins (time + IP). Surfacing this is how a
    player notices a session they didn't create."""
    username = _require_player(authorization)
    with db() as conn:
        rows = conn.execute(
            "SELECT ip, at FROM login_audit WHERE username = ? ORDER BY id DESC LIMIT 20",
            (username,),
        ).fetchall()
    return {"logins": [dict(r) for r in rows]}


@app.post("/arena/submit_team")
def submit_team(req: SubmitTeamRequest, request: Request,
                authorization: str | None = Header(default=None)):
    """Stores the caller's current best team snapshot — the team an
    opponent's challenge will be resolved against. The client computes this
    snapshot exactly as it already does for a normal Tower floor; the
    server does no stat recomputation (see the known-risk note in combat.py
    / the arena plan: a modified client could inflate stats — accepted
    for a friends-scale v1)."""
    username = _require_player(authorization)
    _throttle(request, "write", RL_WRITE)
    # Snapshots are client-computed (this server has no access to any save —
    # see combat.py), so they get normalized and bounded before they can
    # reach the shared combat engine: finite numbers, sane magnitudes, and a
    # bounded skill payload. Cheating a ladder is a tolerated tradeoff;
    # crashing or amplifying against the shared server is not.
    try:
        team = clamp_team(req.team, MAX_TEAM_SIZE)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    payload = json.dumps(team)
    if len(payload.encode()) > MAX_TEAM_JSON_BYTES:
        raise HTTPException(status_code=400, detail="Team payload too large")
    with db() as conn:
        conn.execute(
            "UPDATE arena_players SET team_json = ? WHERE username = ?",
            (payload, username),
        )
    return {"status": "team submitted", "team_size": len(team)}


@app.post("/arena/challenge")
def challenge(req: ChallengeRequest, request: Request,
              authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    # Each call runs a FULL combat simulation and moves ELO/wins/guild-war
    # score. Unlimited, that was both a CPU tap on the shared server and an
    # infinite ladder-farm (challenge the same weak opponent forever).
    _throttle(request, "fight", RL_FIGHT)
    _throttle(request, "fight_user", RL_FIGHT, subject=username)
    opponent = req.opponent.strip()
    if opponent == username:
        raise HTTPException(status_code=400, detail="You can't challenge yourself")

    with db() as conn:
        me = conn.execute(
            "SELECT team_json FROM arena_players WHERE username = ?", (username,)
        ).fetchone()
        them = conn.execute(
            "SELECT team_json FROM arena_players WHERE username = ?", (opponent,)
        ).fetchone()
    if not them:
        raise HTTPException(status_code=404, detail=f"No such player: {opponent}")
    if not me or not me["team_json"]:
        raise HTTPException(status_code=400, detail="Submit your team before challenging (POST /arena/submit_team)")
    if not them["team_json"]:
        raise HTTPException(status_code=400, detail=f"{opponent} hasn't submitted a team yet")

    team_a = json.loads(me["team_json"])
    team_b = json.loads(them["team_json"])
    result = resolve_arena_fight(team_a, team_b)

    winner_username = username if result["winner"] == "heroes" else opponent
    loser_username = opponent if winner_username == username else username

    with db() as conn:
        elo_row_w = conn.execute("SELECT elo FROM arena_players WHERE username = ?", (winner_username,)).fetchone()
        elo_row_l = conn.execute("SELECT elo FROM arena_players WHERE username = ?", (loser_username,)).fetchone()
        old_w, old_l = elo_row_w["elo"] or 1000, elo_row_l["elo"] or 1000
        new_winner_elo, new_loser_elo = update_elo(old_w, old_l)

        conn.execute(
            "UPDATE arena_players SET wins = wins + 1, elo = ? WHERE username = ?", (new_winner_elo, winner_username)
        )
        conn.execute(
            "UPDATE arena_players SET losses = losses + 1, elo = ? WHERE username = ?", (new_loser_elo, loser_username)
        )
        conn.execute(
            "INSERT INTO arena_matches (player1, player2, winner, log_json, timestamp) VALUES (?, ?, ?, ?, ?)",
            (username, opponent, winner_username, json.dumps(result.get("log", [])), time.time()),
        )
        guilds.war_score(conn, winner_username, guilds.WAR_BOUT_SCORE)

    return {
        "winner": winner_username,
        "loser": loser_username,
        "log": result.get("log", []),
        "turns": result.get("turns", []),
        "elo_change": {winner_username: new_winner_elo, loser_username: new_loser_elo},
        # actual deltas — the old elo_change carried the NEW rating, which the
        # client displayed as "+1012"; keep both for stale clients.
        "elo_delta": {winner_username: new_winner_elo - old_w, loser_username: new_loser_elo - old_l},
    }


@app.post("/arena/matchmake")
def matchmake(request: Request, authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    _throttle(request, "fight", RL_FIGHT)
    _throttle(request, "fight_user", RL_FIGHT, subject=username)
    with db() as conn:
        me = conn.execute("SELECT wins, losses, elo, team_json FROM arena_players WHERE username = ?", (username,)).fetchone()
        if not me or not me["team_json"]:
            raise HTTPException(status_code=400, detail="Submit your team before matchmaking")

        my_elo = me["elo"] or 1000

        # Find opponent with the closest ELO rating — a true skill-based pairing
        # now that ELO exists, rather than the old raw net-wins proxy.
        opponent_row = conn.execute(
            """SELECT username, team_json, ABS(COALESCE(elo, 1000) - ?) as diff
               FROM arena_players
               WHERE username != ? AND team_json IS NOT NULL
               ORDER BY diff ASC
               LIMIT 1""",
            (my_elo, username)
        ).fetchone()

    if not opponent_row:
        raise HTTPException(status_code=404, detail="No suitable opponents found. Wait for others to join!")

    # We found an opponent. Proceed to run a challenge exactly like /arena/challenge
    opponent = opponent_row["username"]
    team_a = json.loads(me["team_json"])
    team_b = json.loads(opponent_row["team_json"])
    result = resolve_arena_fight(team_a, team_b)

    winner_username = username if result["winner"] == "heroes" else opponent
    loser_username = opponent if winner_username == username else username

    with db() as conn:
        elo_row_w = conn.execute("SELECT elo FROM arena_players WHERE username = ?", (winner_username,)).fetchone()
        elo_row_l = conn.execute("SELECT elo FROM arena_players WHERE username = ?", (loser_username,)).fetchone()
        old_w, old_l = elo_row_w["elo"] or 1000, elo_row_l["elo"] or 1000
        new_winner_elo, new_loser_elo = update_elo(old_w, old_l)

        conn.execute("UPDATE arena_players SET wins = wins + 1, elo = ? WHERE username = ?", (new_winner_elo, winner_username))
        conn.execute("UPDATE arena_players SET losses = losses + 1, elo = ? WHERE username = ?", (new_loser_elo, loser_username))
        conn.execute(
            "INSERT INTO arena_matches (player1, player2, winner, log_json, timestamp) VALUES (?, ?, ?, ?, ?)",
            (username, opponent, winner_username, json.dumps(result.get("log", [])), time.time()),
        )
        guilds.war_score(conn, winner_username, guilds.WAR_BOUT_SCORE)

    return {
        "opponent": opponent,
        "winner": winner_username,
        "loser": loser_username,
        "log": result.get("log", []),
        "turns": result.get("turns", []),
        "elo_change": {winner_username: new_winner_elo, loser_username: new_loser_elo},
        "elo_delta": {winner_username: new_winner_elo - old_w, loser_username: new_loser_elo - old_l},
    }


@app.get("/arena/my_matches")
def my_matches(limit: int = 10, authorization: str | None = Header(default=None)):
    """The caller's recent bouts, newest first — feeds the RECENT BOUTS
    ledger so it survives a reload."""
    limit = max(1, min(25, limit))
    username = _require_player(authorization)
    with db() as conn:
        rows = conn.execute(
            "SELECT player1, player2, winner, timestamp FROM arena_matches "
            "WHERE player1 = ? OR player2 = ? ORDER BY id DESC LIMIT ?",
            (username, username, limit)).fetchall()
    return {"matches": [
        {"opponent": r["player2"] if r["player1"] == username else r["player1"],
         "won": r["winner"] == username, "winner": r["winner"], "at": r["timestamp"]}
        for r in rows
    ]}


@app.post("/arena/update_floor")
def update_floor(req: UpdateFloorRequest, request: Request,
                 authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    _throttle(request, "write", RL_WRITE)
    # Client-authoritative by design (the server can't verify a local climb),
    # but at least clamp to the game's actual floor range so the PvE
    # leaderboard can't display a 9-digit floor.
    if req.highest_floor < 1 or req.highest_floor > MAX_REPORTED_FLOOR:
        raise HTTPException(status_code=400, detail=f"Floor must be 1-{MAX_REPORTED_FLOOR}")
    with db() as conn:
        old = conn.execute("SELECT highest_floor FROM arena_players WHERE username = ?", (username,)).fetchone()
        old_floor = (old["highest_floor"] or 0) if old else 0
        # Only update if it's strictly greater (so we don't accidentally revert)
        conn.execute(
            "UPDATE arena_players SET highest_floor = ? WHERE username = ? AND highest_floor < ?",
            (req.highest_floor, username, req.highest_floor)
        )
        # Floors gained during a Lodge War bank war score for the guild.
        if req.highest_floor > old_floor:
            guilds.war_score(conn, username, (req.highest_floor - old_floor) * guilds.WAR_FLOOR_SCORE)
    return {"status": "floor updated", "highest_floor": req.highest_floor}


# ─── Guilds v1 (guilds.py; design: docs/guild-social-design.md) ─────

class FoundGuildRequest(BaseModel):
    name: str
    motto: str = ""
    banner: dict = {}

class GuildApplyRequest(BaseModel):
    guild_id: int
    message: str = ""

class GuildDecideRequest(BaseModel):
    app_id: int
    accept: bool

class GuildBuyRequest(BaseModel):
    item_id: str


@app.get("/guild/mine")
def guild_mine(authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        return guilds.my_guild(conn, username)

@app.get("/guild/registry")
def guild_registry(authorization: str | None = Header(default=None)):
    _require_player(authorization)
    with db() as conn:
        return guilds.registry(conn)

@app.post("/guild/found")
def guild_found(req: FoundGuildRequest, authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        return guilds.found_guild(conn, username, req.name, req.motto, req.banner)

@app.post("/guild/apply")
def guild_apply(req: GuildApplyRequest, authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        return guilds.apply_to_guild(conn, username, req.guild_id, req.message)

@app.post("/guild/applications/decide")
def guild_decide(req: GuildDecideRequest, authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        return guilds.decide_application(conn, username, req.app_id, req.accept)

@app.post("/guild/leave")
def guild_leave(authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        return guilds.leave_guild(conn, username)

@app.post("/guild/checkin")
def guild_checkin(authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        return guilds.checkin(conn, username)

@app.post("/guild/boss/strike")
def guild_boss_strike(authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        return guilds.strike_boss(conn, username)

@app.get("/guild/shop")
def guild_shop(authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        return guilds.shop(conn, username)

@app.post("/guild/shop/buy")
def guild_shop_buy(req: GuildBuyRequest, authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        return guilds.shop_buy(conn, username, req.item_id)


@app.get("/guild/perks")
def guild_perks(authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        return guilds.perks(conn, username)


class PerkBuyRequest(BaseModel):
    perk_id: str


@app.post("/guild/perks/buy")
def guild_perk_buy(req: PerkBuyRequest, authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        return guilds.perk_buy(conn, username, req.perk_id)


@app.get("/guild/war")
def guild_war(authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        return guilds.war_status(conn, username)


# ─── The Herald's Wire (chat) ────────────────────────────────────────

class ChatSendRequest(BaseModel):
    channel: str
    text: str
    to: str | None = None


@app.post("/chat/send")
def chat_send(req: ChatSendRequest, authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        return chat.send(conn, username, req.channel, req.text, req.to)


@app.get("/chat/fetch")
def chat_fetch(channel: str, since: int = 0, authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        return chat.fetch(conn, username, channel, since)


@app.get("/chat/whispers")
def chat_whispers(authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        return chat.whisper_threads(conn, username)


@app.get("/chat/whisper/{other}")
def chat_whisper(other: str, since: int = 0, authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        return chat.whisper_thread(conn, username, other, since)


# ─── Social: allies ──────────────────────────────────────────────────

class AllyRequest(BaseModel):
    username: str

class AllyDecideRequest(BaseModel):
    username: str
    accept: bool


@app.get("/social/allies")
def social_allies(authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        return guilds.ally_list(conn, username)

@app.post("/social/invite")
def social_invite(req: AllyRequest, authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        return guilds.ally_invite(conn, username, req.username)

@app.post("/social/decide")
def social_decide(req: AllyDecideRequest, authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        return guilds.ally_decide(conn, username, req.username, req.accept)

@app.post("/social/remove")
def social_remove(req: AllyRequest, authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        return guilds.ally_remove(conn, username, req.username)


MAX_BANNER_JSON_BYTES = 400 * 1024  # paint layer can be a canvas data-URL


@app.post("/arena/banner")
def set_banner(req: BannerRequest, authorization: str | None = Header(default=None)):
    """Carry the player's Banner Studio standard so opponents see it on
    leaderboards and the raid map (the PvP mind-games use case)."""
    username = _require_player(authorization)
    payload = json.dumps(req.banner)
    if len(payload.encode()) > MAX_BANNER_JSON_BYTES:
        raise HTTPException(status_code=400, detail="Banner payload too large")
    with db() as conn:
        conn.execute("UPDATE arena_players SET banner_json = ? WHERE username = ?", (payload, username))
    return {"ok": True}


def _banner_of(row) -> dict | None:
    try:
        return json.loads(row["banner_json"]) if row["banner_json"] else None
    except (json.JSONDecodeError, TypeError):
        return None


@app.get("/arena/leaderboard")
def leaderboard(limit: int = 20):
    with db() as conn:
        pvp_rows = conn.execute(
            "SELECT username, wins, losses, elo, banner_json FROM arena_players "
            "ORDER BY COALESCE(elo, 1000) DESC LIMIT ?",
            (limit,),
        ).fetchall()
        pve_rows = conn.execute(
            "SELECT username, highest_floor FROM arena_players "
            "ORDER BY highest_floor DESC LIMIT ?",
            (limit,),
        ).fetchall()

    return {
        "leaderboard": [
            {"username": r["username"], "wins": r["wins"], "losses": r["losses"], "elo": r["elo"] or 1000,
             "banner": _banner_of(r)}
            for r in pvp_rows
        ],
        "pve_leaderboard": [
            {"username": r["username"], "highest_floor": r["highest_floor"]}
            for r in pve_rows
        ]
    }


@app.get("/arena/health")
def health():
    return {"status": "ok"}


# ─── Seasons & Rewards ────────────────────────────────────────────

class ResetSeasonRequest(BaseModel):
    admin_key: str

@app.post("/arena/admin/reset_season")
def reset_season(req: ResetSeasonRequest):
    # Requires ARENA_ADMIN_KEY in the environment — disabled entirely when
    # unset. compare_digest avoids leaking the key length via timing.
    if not ADMIN_KEY:
        raise HTTPException(status_code=503, detail="Admin actions are not configured on this server")
    if not secrets.compare_digest(req.admin_key, ADMIN_KEY):
        raise HTTPException(status_code=403, detail="Forbidden")
        
    now = time.time()
    with db() as conn:
        # Rank by wins for PvP rewards
        pvp_rows = conn.execute("SELECT username, wins, losses FROM arena_players ORDER BY wins DESC, losses ASC LIMIT 100").fetchall()
        for i, row in enumerate(pvp_rows):
            rank = i + 1
            gems = 0
            if rank == 1:
                gems = 1500
            elif rank <= 3:
                gems = 1000
            elif rank <= 10:
                gems = 500
            elif rank <= 50:
                gems = 200
            else:
                gems = 50
                
            conn.execute(
                "INSERT INTO arena_season_rewards (username, season_end_date, reward_type, amount) VALUES (?, ?, ?, ?)",
                (row["username"], now, "gems", gems)
            )
            
        # Reset PvP scores
        conn.execute("UPDATE arena_players SET wins = 0, losses = 0")
        
    return {"status": "season_reset", "awarded_pvp_ranks": len(pvp_rows)}

@app.get("/arena/my_rewards")
def my_rewards(authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        rows = conn.execute(
            "SELECT id, reward_type, amount, season_end_date FROM arena_season_rewards WHERE username = ? AND claimed = 0",
            (username,)
        ).fetchall()
        
    return {"rewards": [dict(r) for r in rows]}

class ClaimRewardRequest(BaseModel):
    reward_id: int

@app.post("/arena/claim_reward")
def claim_reward(req: ClaimRewardRequest, authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    with db() as conn:
        row = conn.execute(
            "SELECT id, reward_type, amount FROM arena_season_rewards WHERE id = ? AND username = ? AND claimed = 0",
            (req.reward_id, username)
        ).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Reward not found or already claimed.")
            
        conn.execute("UPDATE arena_season_rewards SET claimed = 1 WHERE id = ?", (req.reward_id,))
        
    return {"status": "claimed", "reward_type": row["reward_type"], "amount": row["amount"]}


# ─── Raids (PvP Base Sieges) ──────────────────────────────────────
# Opt-in ecosystem: raiders get a spot on the world map, the ability to
# launch sieges, and a target painted on their own base. Same
# client-snapshot trust model as /arena/submit_team (see that docstring) —
# the defender's base_defense/team and the attacker's team are both
# computed by each player's own local backend and shipped here.

RAID_STEAL_PCT = 0.20            # % of the defender's reported unspent gold / farm ingredients
RAID_SHIELD_SECONDS = 2 * 3600   # a freshly-raided base can't be hit again immediately
MAX_RAID_TEAM_SIZE = MAX_TEAM_SIZE


def _get_player(conn, username: str):
    return conn.execute("SELECT * FROM arena_players WHERE username = ?", (username,)).fetchone()


def _push_raid_event(conn, username: str, event_type: str, payload: dict):
    conn.execute(
        "INSERT INTO raid_events (username, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)",
        (username, event_type, json.dumps(payload), time.time()),
    )


@app.post("/arena/raid/opt_in")
def raid_opt_in(req: RaidOptInRequest, authorization: str | None = Header(default=None)):
    """Toggle raid participation. Opting in places the base at a random free
    cell on the world grid — you can now launch raids, and be raided."""
    username = _require_player(authorization)
    with db() as conn:
        me = _get_player(conn, username)
        if req.enable:
            x, y = me["coord_x"], me["coord_y"]
            if x is None or y is None:
                taken = {(r["coord_x"], r["coord_y"]) for r in conn.execute(
                    "SELECT coord_x, coord_y FROM arena_players WHERE coord_x IS NOT NULL"
                ).fetchall()}
                for _ in range(2000):
                    x, y = random.randrange(WORLD_SIZE), random.randrange(WORLD_SIZE)
                    if (x, y) not in taken:
                        break
                conn.execute(
                    "UPDATE arena_players SET is_raider = 1, coord_x = ?, coord_y = ? WHERE username = ?",
                    (x, y, username),
                )
            else:
                conn.execute("UPDATE arena_players SET is_raider = 1 WHERE username = ?", (username,))
            return {"status": "opted_in", "coordinates": {"x": x, "y": y}}
        else:
            # Opting out delists you as a target AND revokes your raid rights;
            # coordinates are kept so re-opting-in returns you to your plot.
            conn.execute("UPDATE arena_players SET is_raider = 0 WHERE username = ?", (username,))
            return {"status": "opted_out"}


@app.post("/arena/raid/submit_defense")
def submit_defense(req: SubmitDefenseRequest, authorization: str | None = Header(default=None)):
    """Store the caller's defense snapshot: base_defense breakdown (wall/
    garrison/ship/beasts), the hypothetical strongest defending team (top 5),
    docked ship tier, and the lootable resources a successful raider can
    steal from. Built by the caller's local backend (GET /raid/defense_snapshot)."""
    username = _require_player(authorization)
    if not req.defenders:
        raise HTTPException(status_code=400, detail="Defense needs at least one defending hero")
    if len(req.defenders) > MAX_RAID_TEAM_SIZE:
        raise HTTPException(status_code=400, detail=f"At most {MAX_RAID_TEAM_SIZE} defenders")
    if not all(isinstance(h, dict) for h in req.defenders) or not isinstance(req.base_defense, dict):
        raise HTTPException(status_code=400, detail="Malformed defense payload")
    payload = json.dumps({
        "defenders": req.defenders,
        "base_defense": req.base_defense,
        "ship_tier": max(0, min(5, int(req.ship_tier or 0))),
        "lootable": {
            "gold": max(0, int(req.lootable.get("gold", 0) or 0)),
            "ingredients": max(0, int(req.lootable.get("ingredients", 0) or 0)),
        },
        "counter_intel": {
            "total": max(0.0, float(req.counter_intel.get("total", 0) or 0)),
            "breakdown": req.counter_intel.get("breakdown", {}),
        },
    })
    if len(payload.encode()) > MAX_DEFENSE_JSON_BYTES:
        raise HTTPException(status_code=400, detail="Defense payload too large")
    with db() as conn:
        conn.execute(
            "UPDATE arena_players SET defense_json = ?, defense_updated_at = ? WHERE username = ?",
            (payload, time.time(), username),
        )
    return {"status": "defense submitted", "defenders": len(req.defenders)}


@app.get("/arena/raid/map")
def raid_map(radius: int = DEFAULT_SCOUT_RADIUS, authorization: str | None = Header(default=None)):
    """Nearby opted-in bases within a coordinate radius (Chebyshev box) of
    the caller's own base. Defense details stay hidden until scouted."""
    username = _require_player(authorization)
    radius = max(1, min(MAX_SCOUT_RADIUS, radius))
    now = time.time()
    with db() as conn:
        me = _get_player(conn, username)
        if not me["is_raider"] or me["coord_x"] is None:
            raise HTTPException(status_code=400, detail="Opt in to raiding first (POST /arena/raid/opt_in)")
        rows = conn.execute(
            """SELECT username, coord_x, coord_y, elo, highest_floor, defense_json, last_raided_at, banner_json
               FROM arena_players
               WHERE is_raider = 1 AND username != ?
                 AND coord_x BETWEEN ? AND ? AND coord_y BETWEEN ? AND ?""",
            (username, me["coord_x"] - radius, me["coord_x"] + radius,
             me["coord_y"] - radius, me["coord_y"] + radius),
        ).fetchall()
    return {
        "my_coordinates": {"x": me["coord_x"], "y": me["coord_y"]},
        "world_size": WORLD_SIZE,
        "radius": radius,
        "bases": [
            {
                "username": r["username"],
                "x": r["coord_x"], "y": r["coord_y"],
                "distance": max(abs(r["coord_x"] - me["coord_x"]), abs(r["coord_y"] - me["coord_y"])),
                "elo": r["elo"] or 1000,
                "highest_floor": r["highest_floor"],
                "has_defense": bool(r["defense_json"]),
                "banner": _banner_of(r),
                "shielded": bool(r["last_raided_at"] and now - r["last_raided_at"] < RAID_SHIELD_SECONDS),
            }
            for r in rows
        ],
    }


@app.post("/arena/raid/scout")
def raid_scout(req: ScoutRequest, authorization: str | None = Header(default=None)):
    """Scout a target before committing to a siege. Not a flat info-dump:
    the caller's recon rating (scout_power, from their local backend's
    /raid/pay_scout — best Scout-line hero + Mage Tower scrying + battleship
    aerial recon) is graded against the target's counter-intel (patrols,
    wards, counter-spies), and the resulting intel tier (0-4) decides how
    much of the defense report is revealed — from a vague impression through
    a full dossier (see raids.build_scout_report). The Gold/Aether fee is
    charged by the scout's own local backend before this call — same
    client-side economy split as the Training Market's gem cost."""
    username = _require_player(authorization)
    target = req.target.strip()
    if target == username:
        raise HTTPException(status_code=400, detail="That's your own base")
    with db() as conn:
        them = _get_player(conn, target)
    if not them or not them["is_raider"]:
        raise HTTPException(status_code=404, detail=f"No raidable base for: {target}")
    if not them["defense_json"]:
        raise HTTPException(status_code=400, detail=f"{target} hasn't submitted a defense yet")
    defense = json.loads(them["defense_json"])
    # Fuzz-seed on (scout, target, defense version): re-scouting the same
    # defense repeats the same wrong numbers — the noise can't be averaged
    # away — but a resubmitted defense rolls fresh fuzz.
    seed = f"{username}:{target}:{them['defense_updated_at']}"
    report = build_scout_report(defense, req.scout_power, seed)
    report["target"] = target
    return report


@app.post("/arena/raid/attack")
def raid_attack(req: RaidAttackRequest, authorization: str | None = Header(default=None)):
    """Launch the siege. Resolved server-side as a real combat sim with both
    sides' stats shifted by their Base/Ship advantages (see raids.py). The
    victor — invader or defender who repelled them — earns the right to take
    one prisoner from the losing side (POST /arena/raid/claim_prisoner)."""
    username = _require_player(authorization)
    target = req.target.strip()
    if target == username:
        raise HTTPException(status_code=400, detail="You can't raid your own base")
    if not req.team or len(req.team) > MAX_RAID_TEAM_SIZE or not all(isinstance(h, dict) for h in req.team):
        raise HTTPException(status_code=400, detail=f"Attack team must be 1-{MAX_RAID_TEAM_SIZE} hero dicts")
    if len(json.dumps(req.team).encode()) > MAX_TEAM_JSON_BYTES:
        raise HTTPException(status_code=400, detail="Team payload too large")

    now = time.time()
    with db() as conn:
        me = _get_player(conn, username)
        them = _get_player(conn, target)
        if not me["is_raider"]:
            raise HTTPException(status_code=400, detail="Opt in to raiding first (POST /arena/raid/opt_in)")
        if not them or not them["is_raider"]:
            raise HTTPException(status_code=404, detail=f"No raidable base for: {target}")
        if not them["defense_json"]:
            raise HTTPException(status_code=400, detail=f"{target} hasn't submitted a defense yet")
        if them["last_raided_at"] and now - them["last_raided_at"] < RAID_SHIELD_SECONDS:
            mins = int((RAID_SHIELD_SECONDS - (now - them["last_raided_at"])) / 60)
            raise HTTPException(status_code=429, detail=f"{target}'s base is still recovering from the last raid ({mins}m shield left)")

    defense = json.loads(them["defense_json"])
    result = resolve_siege(
        attacker_team=req.team,
        attacker_ship_tier=max(0, min(5, int(req.ship_tier or 0))),
        defender_team=defense["defenders"],
        base_defense=defense.get("base_defense", {}),
        defender_ship_tier=defense.get("ship_tier", 0),
    )

    attacker_won = result["winner"] == "heroes"
    winner, loser = (username, target) if attacker_won else (target, username)
    losing_team = defense["defenders"] if attacker_won else req.team

    spoils = {"gold": 0, "ingredients": 0}
    if attacker_won:
        lootable = defense.get("lootable", {})
        spoils["gold"] = int((lootable.get("gold", 0) or 0) * RAID_STEAL_PCT)
        spoils["ingredients"] = int((lootable.get("ingredients", 0) or 0) * RAID_STEAL_PCT)

    # Survivors of the losing side (they're captured candidates, not corpses:
    # siege knockouts aren't permanent deaths). If the whole losing side was
    # wiped in the sim, every member is a candidate — knocked out and at the
    # victor's mercy is the fiction either way.
    candidates = [
        {
            "id": h.get("id"), "name": h.get("name"), "hero_class": h.get("hero_class"),
            "level": h.get("level", 1), "affinity": h.get("affinity", 50),
            "snapshot": h,
        }
        for h in losing_team
    ]

    with db() as conn:
        cur = conn.execute(
            """INSERT INTO raids (attacker, defender, winner, spoils_json, capture_candidates_json, log_json, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (username, target, winner, json.dumps(spoils), json.dumps(candidates),
             json.dumps(result.get("log", [])), now),
        )
        raid_id = cur.lastrowid
        conn.execute("UPDATE arena_players SET last_raided_at = ? WHERE username = ?", (now, target))
        if attacker_won:
            conn.execute("UPDATE arena_players SET raid_wins = raid_wins + 1 WHERE username = ?", (username,))
            conn.execute("UPDATE arena_players SET defense_losses = defense_losses + 1 WHERE username = ?", (target,))
        else:
            conn.execute("UPDATE arena_players SET raid_losses = raid_losses + 1 WHERE username = ?", (username,))
            conn.execute("UPDATE arena_players SET defense_wins = defense_wins + 1 WHERE username = ?", (target,))
        # The defender wasn't online for this — their inbox tells their client
        # what to apply locally (resource losses; capture comes separately).
        _push_raid_event(conn, target, "raided", {
            "raid_id": raid_id,
            "attacker": username,
            "defended_successfully": not attacker_won,
            "gold_lost": spoils["gold"],
            "ingredients_lost": spoils["ingredients"],
        })

    return {
        "raid_id": raid_id,
        "winner": winner,
        "loser": loser,
        "attacker_won": attacker_won,
        "spoils": spoils,
        "capture_candidates": [
            {k: c[k] for k in ("id", "name", "hero_class", "level", "affinity")}
            for c in candidates
        ] if winner == username else [],
        "siege": result.get("siege"),
        "log": result.get("log", []),
        "turns": result.get("turns", []),
    }


@app.post("/arena/raid/claim_prisoner")
def claim_prisoner(req: ClaimPrisonerRequest, authorization: str | None = Header(default=None)):
    """The raid's victor picks ONE surviving hero from the losing side to
    take prisoner. Returns the full hero snapshot for local integration —
    the captive keeps their original loyalty, so a high-affinity hero enters
    the Rebellious Phase on arrival (see backend /raid/integrate_prisoner)."""
    username = _require_player(authorization)
    with db() as conn:
        raid = conn.execute("SELECT * FROM raids WHERE id = ?", (req.raid_id,)).fetchone()
        if not raid:
            raise HTTPException(status_code=404, detail="Raid not found")
        if raid["winner"] != username:
            raise HTTPException(status_code=403, detail="Only the raid's victor may take prisoners")
        if raid["prisoner_claimed"]:
            raise HTTPException(status_code=409, detail="A prisoner was already taken from this raid")
        candidates = json.loads(raid["capture_candidates_json"] or "[]")
        chosen = next((c for c in candidates if c.get("id") == req.hero_id), None)
        if not chosen:
            raise HTTPException(status_code=404, detail="That hero isn't among the raid's capture candidates")
        loser = raid["defender"] if raid["winner"] == raid["attacker"] else raid["attacker"]
        conn.execute(
            "UPDATE raids SET prisoner_claimed = 1, prisoner_json = ? WHERE id = ?",
            (json.dumps(chosen), req.raid_id),
        )
        _push_raid_event(conn, loser, "hero_captured", {
            "raid_id": req.raid_id,
            "captor": username,
            "hero_id": chosen.get("id"),
            "hero_name": chosen.get("name"),
        })
    return {"status": "captured", "prisoner": chosen["snapshot"], "original_master": loser}


@app.get("/arena/raid/events")
def raid_events(authorization: str | None = Header(default=None)):
    """Unseen raid outcomes for the caller (their base was raided / a hero
    of theirs was captured). Marks them seen — the client applies each one
    to the local save (see backend /raid/apply_raid_event)."""
    username = _require_player(authorization)
    with db() as conn:
        rows = conn.execute(
            "SELECT id, event_type, payload_json, created_at FROM raid_events WHERE username = ? AND seen = 0 ORDER BY id ASC",
            (username,),
        ).fetchall()
        if rows:
            conn.execute("UPDATE raid_events SET seen = 1 WHERE username = ? AND seen = 0", (username,))
    return {"events": [
        {"id": r["id"], "type": r["event_type"], "payload": json.loads(r["payload_json"]), "at": r["created_at"]}
        for r in rows
    ]}


# ─── Server-Wide Tournaments ──────────────────────────────────────

@app.get("/arena/tournaments")
def tournaments_status(authorization: str | None = Header(default=None)):
    """Current week's tournament state: phase (registration Mon-Wed, battles
    Thu-Sat, payouts Sunday), per-format entry counts, the caller's own
    registrations, and standings once a bracket has resolved."""
    username = _require_player(authorization)
    with db() as conn:
        return tournaments.get_status(conn, username)


@app.post("/arena/tournament/register")
def tournament_register(req: TournamentRegisterRequest, authorization: str | None = Header(default=None)):
    """Submit a specific team to one of the week's brackets during the
    Registration Phase (Monday-Wednesday). Team size must match the format:
    1v1 Duels, 2v2 Pairs, 4v4 Warbands, or 5-hero Battle Royale."""
    username = _require_player(authorization)
    if req.format not in TOURNAMENT_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unknown format. One of: {', '.join(TOURNAMENT_FORMATS)}")
    required = TOURNAMENT_FORMATS[req.format]
    if len(req.team) != required or not all(isinstance(h, dict) for h in req.team):
        raise HTTPException(status_code=400, detail=f"The {req.format} bracket takes exactly {required} hero(es)")
    if len(json.dumps(req.team).encode()) > MAX_TEAM_JSON_BYTES:
        raise HTTPException(status_code=400, detail="Team payload too large")
    with db() as conn:
        return tournaments.register(conn, username, req.format, req.team)


@app.get("/arena/tournament/standings")
def tournament_standings(format: str, week: str | None = None, authorization: str | None = Header(default=None)):
    """Bracket standings. During Thu-Sat this lazily runs the bracket's
    auto-battler rounds the first time anyone asks; on Sunday it also
    triggers payouts (top of the leaderboard gets Summon Tickets and an
    exclusive Cosmetic in their reward inbox)."""
    _require_player(authorization)
    if format not in TOURNAMENT_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unknown format. One of: {', '.join(TOURNAMENT_FORMATS)}")
    with db() as conn:
        return tournaments.get_standings(conn, format, week)


# ─── Training Market ──────────────────────────────────────────────

class ListTeacherRequest(BaseModel):
    hero_name: str
    hero_class: str
    hero_stats: dict
    hero_skills: list
    gem_cost: int

@app.post("/arena/market/list")
def list_teacher(req: ListTeacherRequest, request: Request,
                 authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    _throttle(request, "market", RL_MARKET)
    if req.gem_cost < 0 or req.gem_cost > MAX_GEM_COST:
        raise HTTPException(status_code=400, detail=f"Gem cost must be 0-{MAX_GEM_COST}.")
    if len(req.hero_name) > 40 or len(req.hero_class) > 40:
        raise HTTPException(status_code=400, detail="Hero name/class too long.")
    if len(json.dumps(req.hero_stats).encode()) > MAX_MARKET_JSON_BYTES or len(json.dumps(req.hero_skills).encode()) > MAX_MARKET_JSON_BYTES:
        raise HTTPException(status_code=400, detail="Listing payload too large.")
        
    with db() as conn:
        # Check how many they have listed to prevent spam
        count = conn.execute("SELECT COUNT(*) as c FROM training_market WHERE username = ?", (username,)).fetchone()["c"]
        if count >= 3:
            raise HTTPException(status_code=400, detail="You can only list up to 3 teachers at a time.")
            
        conn.execute(
            """INSERT INTO training_market 
               (username, hero_name, hero_class, hero_stats_json, hero_skills_json, gem_cost, listed_at) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (username, req.hero_name, req.hero_class, json.dumps(req.hero_stats), json.dumps(req.hero_skills), req.gem_cost, time.time())
        )
    return {"status": "listed"}

@app.get("/arena/market")
def get_training_market(authorization: str | None = Header(default=None)):
    _require_player(authorization)
    with db() as conn:
        rows = conn.execute("SELECT * FROM training_market ORDER BY listed_at DESC LIMIT 50").fetchall()
        
    return {"listings": [
        {
            "id": r["id"],
            "username": r["username"],
            "hero_name": r["hero_name"],
            "hero_class": r["hero_class"],
            "hero_stats": json.loads(r["hero_stats_json"]),
            "hero_skills": json.loads(r["hero_skills_json"]),
            "gem_cost": r["gem_cost"]
        } for r in rows
    ]}

class HireTeacherRequest(BaseModel):
    listing_id: int

# Training-market payout guardrails. This endpoint MINTS premium currency
# (gem rows in the reward inbox, which the game claims into a real save), so
# every one of these limits is load-bearing:
#   - one paid hire per (hirer, listing), enforced by a UNIQUE key
#   - a daily payout ceiling per listing, so one popular teacher can't be
#     farmed by a crowd of throwaway accounts
#   - hirers must be established accounts, not minutes-old registrations
MARKET_PAYOUTS_PER_LISTING_PER_DAY = 5
MARKET_HIRER_MIN_FLOOR = 5


@app.post("/arena/market/hire")
def hire_teacher(req: HireTeacherRequest, request: Request,
                 authorization: str | None = Header(default=None)):
    username = _require_player(authorization)
    _throttle(request, "market", RL_MARKET)
    _throttle(request, "market_user", RL_MARKET, subject=username)
    now = time.time()
    with db() as conn:
        listing = conn.execute("SELECT * FROM training_market WHERE id = ?", (req.listing_id,)).fetchone()
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found.")
        if listing["username"] == username:
            raise HTTPException(status_code=400, detail="You cannot hire your own teacher.")

        already = conn.execute(
            "SELECT 1 FROM market_hires WHERE listing_id = ? AND hirer = ?",
            (req.listing_id, username),
        ).fetchone()

        # The teacher's knowledge is re-deliverable (the client already paid
        # locally the first time) — but the LISTER is only ever paid once per
        # hirer, and only within the daily ceiling.
        pay = False
        if not already and listing["gem_cost"] > 0:
            me = conn.execute(
                "SELECT highest_floor FROM arena_players WHERE username = ?", (username,)
            ).fetchone()
            if (me["highest_floor"] or 0) < MARKET_HIRER_MIN_FLOOR:
                raise HTTPException(
                    status_code=403,
                    detail=f"Reach floor {MARKET_HIRER_MIN_FLOOR} before hiring from the market.",
                )
            paid_today = conn.execute(
                "SELECT COUNT(*) AS c FROM market_hires WHERE listing_id = ? AND at > ?",
                (req.listing_id, now - 86400),
            ).fetchone()["c"]
            if paid_today >= MARKET_PAYOUTS_PER_LISTING_PER_DAY:
                raise HTTPException(
                    status_code=429,
                    detail="This teacher has taken on all the students they can today.",
                )
            pay = True

        if not already:
            conn.execute(
                "INSERT OR IGNORE INTO market_hires (listing_id, hirer, at) VALUES (?, ?, ?)",
                (req.listing_id, username, now),
            )
        if pay:
            conn.execute(
                "INSERT INTO arena_season_rewards (username, season_end_date, reward_type, amount) VALUES (?, ?, ?, ?)",
                (listing["username"], now, "gems", min(int(listing["gem_cost"]), MAX_GEM_COST)),
            )

    return {
        "status": "hired",
        "already_hired": bool(already),
        "teacher": {
            "hero_name": listing["hero_name"],
            "hero_class": listing["hero_class"],
            "hero_stats": json.loads(listing["hero_stats_json"]),
            "hero_skills": json.loads(listing["hero_skills_json"]),
            "gem_cost": listing["gem_cost"]
        }
    }
