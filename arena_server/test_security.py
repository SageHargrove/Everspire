"""
Security regression tests for the world/arena server.

Each test encodes a REAL exploit that worked against this server before the
2026-07-12 hardening pass. Run from arena_server/:

    python test_security.py

Uses a throwaway DB (ARENA_DB_PATH) so it never touches live data.
"""
import os
import sys
import tempfile

os.environ["ARENA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test_arena.db")
os.environ["ARENA_ADMIN_KEY"] = "test-admin-key-long-enough"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import security  # noqa: E402
import guilds  # noqa: E402
import chat  # noqa: E402
from database import db, init_db  # noqa: E402

# TestClient only fires @app.on_event("startup") inside a context manager, so
# build the schema explicitly here.
init_db()
with db() as _c:
    guilds.init_tables(_c)
    chat.init_tables(_c)

client = TestClient(main.app)
PASSED, FAILED = [], []


def check(name, condition, detail=""):
    (PASSED if condition else FAILED).append(name)
    print(f"  {'PASS' if condition else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not condition else ""))


def fresh(username, floor=50):
    """Register an account, return its bearer headers."""
    security.reset_limits()
    r = client.post("/auth/register", json={
        "email": f"{username}@example.com", "username": username, "password": "correct-horse"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    if floor:
        security.reset_limits()
        client.post("/arena/update_floor", json={"highest_floor": floor}, headers=h)
    return h


TEAM = [{"id": 1, "name": "Tester", "hero_class": "Warrior", "health": 300, "max_health": 300,
         "strength": 40, "intelligence": 10, "agility": 20, "endurance": 20}]

print("\n=== CRITICAL: training market minted unlimited premium currency ===")
# Exploit (pre-fix): A lists a teacher; B calls /market/hire in a loop. Each
# call inserted a gem reward row for A and charged B nothing, with no
# idempotency — then A claims the rows into a real save. Infinite gems.
seller = fresh("gemseller")
buyer = fresh("gembuyer")
security.reset_limits()
client.post("/arena/market/list", json={
    "hero_name": "Sage", "hero_class": "Mage", "hero_stats": {"strength": 10},
    "hero_skills": [], "gem_cost": 1000}, headers=seller)
listing_id = client.get("/arena/market", headers=buyer).json()["listings"][0]["id"]

security.reset_limits()
ok_count = 0
for _ in range(10):
    security.reset_limits()          # isolate the economy fix from the rate limiter
    if client.post("/arena/market/hire", json={"listing_id": listing_id}, headers=buyer).status_code == 200:
        ok_count += 1
with db() as conn:
    minted = conn.execute(
        "SELECT COALESCE(SUM(amount),0) AS s FROM arena_season_rewards WHERE username = 'gemseller'"
    ).fetchone()["s"]
check("10 repeat hires mint at most ONE payout", minted <= 1000, f"minted {minted} gems")
check("repeat hires still deliver the teacher (not a hard error)", ok_count >= 2, f"{ok_count}/10 succeeded")

# Fresh accounts can't farm payouts either: gated on real progress.
security.reset_limits()
newbie = fresh("freshmeat", floor=0)
security.reset_limits()
r = client.post("/arena/market/hire", json={"listing_id": listing_id}, headers=newbie)
check("brand-new account (floor 0) is refused a paid hire", r.status_code == 403, f"got {r.status_code}")

# Per-listing daily ceiling caps a crowd of throwaway accounts.
security.reset_limits()
paid = 0
for i in range(9):
    h = fresh(f"farmer{i}")
    security.reset_limits()
    if client.post("/arena/market/hire", json={"listing_id": listing_id}, headers=h).status_code == 200:
        paid += 1
check("per-listing daily payout ceiling holds",
      paid <= main.MARKET_PAYOUTS_PER_LISTING_PER_DAY, f"{paid} paid hires got through")

print("\n=== HIGH: unauthenticated body-size DoS ===")
# Pre-fix: FastAPI buffered the entire body before validation, so one POST
# with a giant body was an OOM kill — no auth required.
big = "x" * (400 * 1024)
security.reset_limits()
r = client.post("/auth/login", json={"identifier": big, "password": big})
check("oversized body rejected with 413", r.status_code == 413, f"got {r.status_code}")

print("\n=== HIGH: rate limiting on expensive + auth endpoints ===")
security.reset_limits()
codes = [client.post("/auth/login", json={"identifier": "nobody", "password": "wrong"}).status_code
         for _ in range(30)]
check("login brute force is throttled (429 appears)", 429 in codes,
      f"no 429 in {len(codes)} attempts")
check("throttle is not a lockout of the victim account",
      codes.count(401) >= 15, f"401s: {codes.count(401)}")

security.reset_limits()
reg_codes = [client.post("/auth/register", json={
    "email": f"spam{i}@x.com", "username": f"spam{i}", "password": "correct-horse"}).status_code
    for i in range(30)]
check("unlimited account creation is throttled", 429 in reg_codes, "no 429 while spamming register")

fighter = fresh("fighter")
security.reset_limits()
client.post("/arena/submit_team", json={"team": TEAM}, headers=fighter)
security.reset_limits()
fight_codes = [client.post("/arena/matchmake", headers=fighter).status_code for _ in range(40)]
check("combat endpoints are throttled (CPU + ELO farming)", 429 in fight_codes,
      "matchmake never throttled")

print("\n=== HIGH: session tokens hashed at rest ===")
security.reset_limits()
r = client.post("/auth/register", json={
    "email": "hash@example.com", "username": "hashme", "password": "correct-horse"})
plaintext = r.json()["token"]
with db() as conn:
    stored = conn.execute("SELECT token FROM arena_players WHERE username = 'hashme'").fetchone()["token"]
check("DB does not contain the plaintext token", stored != plaintext, "token stored verbatim")
check("stored value is the sha256 of the token", stored == security.hash_token(plaintext))
check("the plaintext token still authenticates",
      client.get("/auth/me", headers={"Authorization": f"Bearer {plaintext}"}).status_code == 200)

# A stolen DB gives an attacker only the hash — replaying it must fail.
check("replaying the STORED hash as a bearer token fails",
      client.get("/auth/me", headers={"Authorization": f"Bearer {stored}"}).status_code == 401)

print("\n=== HIGH: hostile hero snapshots are clamped ===")
# Pre-fix: submitted stats went to the shared combat engine unvalidated —
# absurd magnitudes, NaN/inf, and unbounded skill `actions` arrays (a CPU +
# combat-log amplification vector).
hostile = fresh("hostile")
security.reset_limits()
# Sent as RAW body text: Python's json.loads accepts the non-standard
# `Infinity` literal, which is exactly how a hand-rolled attacker payload
# would smuggle a non-finite stat past a naive client library.
import json as _json  # noqa: E402
hostile_hero = {
    "id": 1, "name": "X" * 500, "hero_class": "Warrior",
    "health": 10**12, "max_health": 10**12,
    "strength": 10**9, "agility": "not-a-number",
    "crit_chance": 99.0, "portrait_path": "../../../etc/passwd",
    # Sized to fit UNDER the 256 KB body cap so it actually reaches the
    # clamping logic — the oversized variant is covered separately below.
    "_skills": [{"id": "evil", "name": "Boom", "type": "active",
                 "effect": {"actions": [{"kind": "damage", "power": 9e9}] * 120}}] * 30,
}
raw = _json.dumps({"team": [hostile_hero]})
raw = raw.replace('"strength": 1000000000', '"strength": 1000000000, "intelligence": Infinity')
assert len(raw) < 256 * 1024, f"test payload {len(raw)}B must stay under the body cap"
r = client.post("/arena/submit_team", content=raw.encode(),
                headers={**hostile, "Content-Type": "application/json"})
check("hostile snapshot is accepted-but-normalized (no 500)", r.status_code == 200, f"got {r.status_code}")
with db() as conn:
    stored_team = conn.execute(
        "SELECT team_json FROM arena_players WHERE username = 'hostile'").fetchone()["team_json"]
import json  # noqa: E402
if not stored_team:
    check("hostile snapshot stored for inspection", False, "submit_team stored nothing")
    h0 = {"strength": 0, "max_health": 0, "intelligence": 0, "agility": 0,
          "crit_chance": 0.0, "portrait_path": "", "_skills": [], "name": ""}
else:
    h0 = json.loads(stored_team)[0]
check("strength clamped", h0["strength"] <= security.MAX_STAT, f"strength={h0['strength']}")
check("max_health clamped", h0["max_health"] <= security.MAX_HEALTH, f"hp={h0['max_health']}")
check("non-finite intelligence neutralized", h0["intelligence"] <= security.MAX_STAT)
check("non-numeric agility coerced", isinstance(h0["agility"], int))
check("crit_chance bounded to 0..1", 0.0 <= h0["crit_chance"] <= 1.0, f"crit={h0['crit_chance']}")
check("traversal-y portrait path stripped", h0["portrait_path"] == "", f"got {h0['portrait_path']!r}")
check("skill count bounded", len(h0["_skills"]) <= security.MAX_SKILLS_PER_HERO,
      f"{len(h0['_skills'])} skills")
check("skill actions bounded (amplification closed)",
      all(len(s["effect"].get("actions", [])) <= security.MAX_ACTIONS_PER_SKILL for s in h0["_skills"]))
check("name length bounded", len(h0["name"]) <= security.MAX_NAME_LEN)

# Defense in depth: the same attack scaled past the body cap dies earlier,
# before anything is buffered or parsed.
security.reset_limits()
huge = _json.dumps({"team": [{**hostile_hero, "_skills": [
    {"id": "evil", "name": "Boom", "type": "active",
     "effect": {"actions": [{"kind": "damage", "power": 9e9}] * 4000}}] * 50}]})
r = client.post("/arena/submit_team", content=huge.encode(),
                headers={**hostile, "Content-Type": "application/json"})
check("oversized amplification payload dies at the body cap", r.status_code == 413,
      f"got {r.status_code} for a {len(huge)}B body")

print("\n=== MED: security headers present ===")
r = client.get("/")
for header, expected in [("x-content-type-options", "nosniff"),
                         ("x-frame-options", "DENY"),
                         ("referrer-policy", "no-referrer")]:
    check(f"{header} set", r.headers.get(header) == expected, f"got {r.headers.get(header)!r}")
check("CSP forbids framing", "frame-ancestors 'none'" in (r.headers.get("content-security-policy") or ""))
check("HSTS set", "max-age=" in (r.headers.get("strict-transport-security") or ""))

print("\n=== IDOR / cross-account access (verifying these were already safe) ===")
a = fresh("victim_a")
b = fresh("attacker_b")
security.reset_limits()
with db() as conn:
    conn.execute("INSERT INTO arena_season_rewards (username, season_end_date, reward_type, amount) "
                 "VALUES ('victim_a', 0, 'gems', 500)")
    rid = conn.execute("SELECT id FROM arena_season_rewards WHERE username='victim_a'").fetchone()["id"]
r = client.post("/arena/claim_reward", json={"reward_id": rid}, headers=b)
check("cannot claim another player's reward by id", r.status_code == 404, f"got {r.status_code}")
with db() as conn:
    still = conn.execute("SELECT claimed FROM arena_season_rewards WHERE id = ?", (rid,)).fetchone()["claimed"]
check("victim's reward remains unclaimed", still == 0)
check("owner CAN claim their own reward",
      client.post("/arena/claim_reward", json={"reward_id": rid}, headers=a).status_code == 200)

print("\n=== admin surface ===")
r = client.post("/arena/admin/reset_season", json={"admin_key": "wrong-key"})
check("wrong admin key is refused", r.status_code == 403, f"got {r.status_code}")
r = client.post("/arena/admin/reset_season", json={"admin_key": "x" * 200})
check("admin key length mismatch doesn't 500", r.status_code == 403, f"got {r.status_code}")

print("\n" + "=" * 62)
print(f"  {len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    for f in FAILED:
        print(f"    FAILED: {f}")
print("=" * 62)
sys.exit(1 if FAILED else 0)
