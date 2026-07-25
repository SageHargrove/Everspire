"""
Arena/World server hardening primitives.

This server is the ONE piece of Tower of Eternity exposed to the open
internet (Caddy fronts it; the game client is the only intended caller).
Everything here exists because "the client is a game client" is not a
security boundary — anyone can curl these endpoints.

Contents:
  client_ip()                 real caller IP behind Caddy (X-Forwarded-For aware)
  rate_limit()                in-memory sliding-window limiter, keyed by IP or user
  BodySizeLimitMiddleware     rejects oversized request bodies BEFORE parsing
  SecurityHeadersMiddleware   nosniff / frame-ancestors / referrer / HSTS
  hash_token()                session tokens are stored hashed, never plaintext
  clamp_hero_snapshot()       plausibility caps on client-submitted hero stats
"""
from __future__ import annotations

import hashlib
import os
import time
from collections import deque

# ─── real client IP behind the reverse proxy ─────────────────────────
#
# Caddy appends the immediate peer to X-Forwarded-For, so the LAST entry is
# the address Caddy actually saw. Earlier entries are attacker-controllable
# (a client can send its own XFF header), so we never trust those — using
# the last hop is what makes IP-keyed rate limiting meaningful here.
# TRUST_PROXY=0 disables XFF parsing entirely (direct-exposure deployments).
_TRUST_PROXY = os.environ.get("ARENA_TRUST_PROXY", "1") != "0"


def _is_local_peer(host: str) -> bool:
    """True for loopback / RFC1918 / Docker-bridge peers — i.e. the only
    places our own reverse proxy can legitimately be."""
    if not host:
        return False
    if host in ("127.0.0.1", "::1", "localhost", "testclient"):
        return True
    if host.startswith(("10.", "192.168.", "172.")):
        # 172.16.0.0/12 covers Docker's default bridge range.
        if host.startswith("172."):
            try:
                second = int(host.split(".")[1])
            except (IndexError, ValueError):
                return False
            return 16 <= second <= 31
        return True
    return False


def client_ip(request) -> str:
    """The caller's real address, for rate-limit keying.

    X-Forwarded-For is only honoured when the DIRECT peer is our own proxy
    (loopback/private). A client connecting straight to the port can set any
    XFF value it likes, so trusting it unconditionally would hand every
    attacker a free rate-limit bypass: rotate the header, rotate the bucket.
    """
    peer = (request.client.host if request.client else "") or ""
    if _TRUST_PROXY and _is_local_peer(peer):
        xff = request.headers.get("x-forwarded-for")
        if xff:
            last = xff.split(",")[-1].strip()
            if last:
                return last
        real = request.headers.get("x-real-ip")
        if real:
            return real.strip()
    return peer or "unknown"


# ─── sliding-window rate limiter ─────────────────────────────────────
#
# In-memory and per-process: resets on restart and doesn't span replicas.
# That is a deliberate fit for a single-container hobby deployment — it
# stops scripted abuse, which is the actual threat, without dragging Redis
# into the stack. _MAX_KEYS bounds memory so an attacker rotating source
# IPs can't grow the table without limit.
_buckets: dict[str, deque] = {}
_MAX_KEYS = 20_000


def rate_limit(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """Returns (allowed, retry_after_seconds). Call once per request."""
    now = time.time()
    dq = _buckets.get(key)
    if dq is None:
        if len(_buckets) >= _MAX_KEYS:
            # Evict the least recently touched half rather than growing forever.
            for k in sorted(_buckets, key=lambda k: _buckets[k][-1] if _buckets[k] else 0)[: _MAX_KEYS // 2]:
                _buckets.pop(k, None)
        dq = _buckets[key] = deque()
    cutoff = now - window_seconds
    while dq and dq[0] < cutoff:
        dq.popleft()
    if len(dq) >= limit:
        return False, max(1, int(window_seconds - (now - dq[0])))
    dq.append(now)
    return True, 0


def reset_limits() -> None:
    """Test hook — clears every bucket."""
    _buckets.clear()


# ─── request body cap ────────────────────────────────────────────────
#
# FastAPI reads the entire body into memory before validation runs, so a
# single unauthenticated POST with a 1 GB body is an out-of-memory kill
# regardless of how strict the Pydantic model is. Per-endpoint payload
# checks (MAX_TEAM_JSON_BYTES etc.) all run far too late to prevent that.
class BodySizeLimitMiddleware:
    """Pure-ASGI so it can reject before the body is ever buffered."""

    def __init__(self, app, max_bytes: int = 256 * 1024):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        headers = {k.lower(): v for k, v in (scope.get("headers") or [])}
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                if int(declared) > self.max_bytes:
                    return await self._reject(send)
            except (ValueError, TypeError):
                pass

        # Chunked / undeclared bodies: count as they stream in.
        total = 0
        started = False
        too_large = False

        async def guarded_receive():
            nonlocal total, too_large
            message = await receive()
            if message.get("type") == "http.request":
                total += len(message.get("body") or b"")
                if total > self.max_bytes:
                    too_large = True
                    # Starve the app of further body; it will fail validation
                    # and we replace the response below.
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message):
            nonlocal started
            if message.get("type") == "http.response.start":
                if too_large and not started:
                    started = True
                    return await self._reject(send)
                started = True
            if too_large and not started:
                return
            await send(message)

        await self.app(scope, guarded_receive, guarded_send)

    async def _reject(self, send):
        body = b'{"detail":"Request body too large"}'
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})


# ─── security headers ────────────────────────────────────────────────
#
# This service returns JSON, but it IS browser-reachable on a public
# hostname, so the cheap defenses still apply: no MIME sniffing, no
# framing (clickjacking), no referrer leakage, and HSTS since Caddy
# terminates TLS. A restrictive CSP is safe precisely because no page
# here needs to load anything.
class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message.get("type") == "http.response.start":
                headers = message.setdefault("headers", [])
                drop = {b"server", b"x-powered-by"}
                headers[:] = [(k, v) for k, v in headers if k.lower() not in drop]
                headers.extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"content-security-policy",
                     b"default-src 'none'; frame-ancestors 'none'; base-uri 'none'"),
                    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
                    (b"cache-control", b"no-store"),
                ])
            await send(message)

        await self.app(scope, receive, send_with_headers)


# ─── session tokens: hashed at rest ──────────────────────────────────
#
# Tokens were stored in plaintext, so any read of arena.db (backup, volume
# snapshot, SQL-injection-adjacent bug) handed over every live session for
# its full 7-day lifetime. They're 256 bits of secrets.token_hex entropy —
# unguessable, so a plain SHA-256 is the right primitive here (no need for
# a slow KDF: there's no low-entropy secret to brute force).
# Stored values carry a version prefix. That prefix is what makes the
# legacy-plaintext migration path safe: without it, a stolen DB value (a bare
# 64-hex digest) is indistinguishable from a real 64-hex token, so replaying
# the digest as a bearer token would sail through the legacy lookup and
# hashing-at-rest would buy nothing. See _require_player's NOT LIKE guard.
TOKEN_HASH_PREFIX = "v2:"


def hash_token(token: str) -> str:
    return TOKEN_HASH_PREFIX + hashlib.sha256(token.encode()).hexdigest()


# ─── plausibility caps on client-submitted hero snapshots ────────────
#
# The arena is client-authoritative by design (this server has no access to
# anyone's save, so it cannot recompute stats — see combat.py). That means a
# modified client CAN submit a stronger team than it really owns; accepted
# for a friends-scale ladder. What is NOT acceptable is a submission that
# breaks the shared server: absurd magnitudes distort every fight, and a
# crafted skill payload is a CPU/log amplification vector. These caps keep
# submissions inside "a very strong legitimate hero" and no further.
MAX_STAT = 100_000          # a maxed legitimate hero lands orders of magnitude below this
MAX_HEALTH = 5_000_000
MAX_SKILLS_PER_HERO = 12    # matches the largest real class kit
MAX_ACTIONS_PER_SKILL = 8   # real skills use 1-3
MAX_NAME_LEN = 40

_INT_STATS = ("strength", "intelligence", "agility", "endurance", "willpower",
              "luck", "defense", "level", "morale", "stress", "trauma")
# Fields combat_service indexes directly on a hero dict — always emitted.
_REQUIRED_INT_STATS = ("strength", "intelligence", "agility", "morale", "stress")
_STAT_DEFAULTS = {"morale": 100, "stress": 0, "trauma": 0, "level": 1,
                  "strength": 10, "intelligence": 10, "agility": 10,
                  "endurance": 5, "willpower": 6, "luck": 5, "defense": 5}
_FLOAT_STATS = ("crit_chance", "dodge_chance", "dmg_reduction_pct", "armor_pen",
                "physical_resist_pct", "magic_resist_pct", "regen_pct")


def _num(value, lo, hi, default):
    """Coerce a client value into a number inside [lo, hi]. Non-numeric or
    NaN/inf input falls back to `default` — never propagates into combat."""
    try:
        if isinstance(value, bool) or value is None:
            return default
        n = float(value)
        if n != n or n in (float("inf"), float("-inf")):
            return default
        return max(lo, min(hi, n))
    except (TypeError, ValueError):
        return default


def clamp_hero_snapshot(hero: dict) -> dict:
    """Normalize ONE client-submitted hero dict into something the combat
    engine can safely consume: required fields present, numbers finite and
    bounded, skill payloads bounded. Unknown extra keys are dropped."""
    if not isinstance(hero, dict):
        raise ValueError("hero must be an object")

    out: dict = {}
    out["id"] = int(_num(hero.get("id"), -10**9, 10**9, 0))
    name = hero.get("name")
    out["name"] = (str(name)[:MAX_NAME_LEN] if isinstance(name, (str, int, float)) else "Unknown")
    hero_class = hero.get("hero_class")
    out["hero_class"] = (str(hero_class)[:MAX_NAME_LEN] if isinstance(hero_class, str) else "Classless")

    out["max_health"] = int(_num(hero.get("max_health"), 1, MAX_HEALTH, 100))
    out["health"] = int(_num(hero.get("health"), 1, out["max_health"], out["max_health"]))

    # The combat engine indexes some hero fields directly (h["morale"],
    # h["stress"], h["agility"]...), so a missing one is a 500 rather than a
    # default. Emit every required key unconditionally — this normalizer is
    # the gatekeeper, so it owns satisfying the engine's contract.
    for key in _INT_STATS:
        if key in hero or key in _REQUIRED_INT_STATS:
            out[key] = int(_num(hero.get(key), 0, MAX_STAT, _STAT_DEFAULTS.get(key, 5)))
    for key in _FLOAT_STATS:
        if key in hero:
            out[key] = _num(hero.get(key), 0.0, 1.0, 0.0)

    for key in ("is_ranged", "is_aoe", "has_construct", "fear_immune", "is_team_leader"):
        if key in hero:
            out[key] = bool(hero.get(key))

    power_stat = hero.get("power_stat")
    out["power_stat"] = power_stat if power_stat in ("strength", "intelligence") else "strength"
    out["death_save"] = int(_num(hero.get("death_save"), 0, 3, 0))
    out["hero_star"] = int(_num(hero.get("hero_star") or hero.get("birth_star"), 1, 7, 1))
    out["birth_star"] = out["hero_star"]
    tendency = hero.get("battle_tendency")
    out["battle_tendency"] = str(tendency)[:32] if isinstance(tendency, str) else "Stoic"
    portrait = hero.get("portrait_path")
    # Path is echoed back to other clients as an <img> src — keep it a plain
    # relative asset path (no scheme, no traversal, no protocol-relative URL).
    if isinstance(portrait, str) and len(portrait) <= 200 and ".." not in portrait \
            and ":" not in portrait and not portrait.startswith("//"):
        out["portrait_path"] = portrait
    else:
        out["portrait_path"] = ""

    for apt in ("apt_combat", "apt_tactical", "apt_survival", "apt_mental",
                "apt_leadership", "apt_magic"):
        if apt in hero:
            out[apt] = int(_num(hero.get(apt), 0, 1000, 50))

    out["_skills"] = _clamp_skills(hero.get("_skills") or hero.get("skills"))
    return out


def _clamp_skills(skills) -> list:
    """Bound the skill payload. Unbounded `actions` arrays were a real
    amplification vector: a 64 KB team could carry thousands of actions,
    each one applied per cast per round, inflating CPU and the stored
    combat log into the tens of megabytes."""
    if not isinstance(skills, list):
        return []
    safe = []
    for raw in skills[:MAX_SKILLS_PER_HERO]:
        if not isinstance(raw, dict):
            continue
        eff_in = raw.get("effect") if isinstance(raw.get("effect"), dict) else {}
        eff: dict = {}
        for k, v in list(eff_in.items())[:24]:
            if k in ("actions", "self_actions"):
                if isinstance(v, list):
                    eff[k] = [a for a in v[:MAX_ACTIONS_PER_SKILL] if isinstance(a, dict)]
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                eff[k] = _num(v, -10_000, 10_000, 0)
            elif isinstance(v, bool):
                eff[k] = v
            elif isinstance(v, str):
                eff[k] = v[:40]
        safe.append({
            "id": str(raw.get("id", ""))[:60],
            "name": str(raw.get("name", "Skill"))[:MAX_NAME_LEN],
            "type": raw.get("type") if raw.get("type") in ("active", "passive", "boss_drop") else "passive",
            "effect": eff,
        })
    return safe


def clamp_team(team, max_size: int) -> list:
    """Validate + clamp a whole submitted team."""
    if not isinstance(team, list) or not team:
        raise ValueError("Team cannot be empty")
    if len(team) > max_size:
        raise ValueError(f"Teams are at most {max_size} heroes")
    return [clamp_hero_snapshot(h) for h in team]
