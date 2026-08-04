# Security review — Giltgrave (2026-07-12)

Adversarial application-layer review of both halves of the game, plus the
fixes applied. Regression tests live in `arena_server/test_security.py`
(34 checks, each encoding an exploit that previously worked).

```
cd arena_server && python test_security.py
```

---

## 1. Attack surface

The brief described a live `world-server` container behind Caddy. In this
repo that is **`arena_server/`** — and it is the only internet-exposed
component. The two halves have very different threat models:

| | `arena_server/` (world server) | `backend/` (local game) |
|---|---|---|
| Exposure | **Public internet** via Caddy → `127.0.0.1:8001` | localhost only, inside the packaged desktop app |
| Stack | FastAPI + uvicorn, SQLite (`arena.db`), bcrypt | FastAPI + uvicorn, SQLite (`game.db`) |
| Auth | Bearer token (opaque, 256-bit, server-side, 7-day expiry) | **None by design** — it owns one local save |
| Owns | Accounts, ELO/ladder, guilds, chat, raids, tournaments, training market, season rewards | Everything single-player: heroes, gold/gems, tower progress |
| Realtime | None (HTTP polling only — no WebSocket surface) | None |
| Outbound | None | LLM calls (Anthropic/Gemini) + local ComfyUI |
| Routes | 53 | 186 |

**Trust boundaries.** Everything from the game client is untrusted input.
The world server additionally cannot recompute hero stats — it has no access
to any player's save — so team/defense snapshots are *inherently*
client-authoritative (see §4).

**Reachable without a token:** `GET /`, `GET /arena/health`,
`GET /arena/leaderboard`, `POST /auth/register`, `POST /auth/login`,
`POST /arena/register`, `POST /arena/login`, `POST /arena/admin/reset_season`
(env-key gated). Everything else calls `_require_player`.

---

## 2. Findings

### CRITICAL — 1

**C1. `/arena/market/hire` minted unlimited premium currency.**

*Exploit path.* Register two accounts (registration was free and
unthrottled). Account **A** lists a teacher at `gem_cost: 1000`. Account
**B** POSTs `/arena/market/hire {"listing_id": N}` in a loop. Every call
inserted a 1000-gem row into `arena_season_rewards` **for A**, charged B
nothing server-side, and had no idempotency or repeat check. A then opens the
game, where `ArenaPage` auto-claims every reward row into local mail →
`UPDATE base SET gems = gems + ?`. Ten seconds of scripting = millions of
real gems, the currency that buys summons.

*Fix.* `market_hires` table with a `(listing_id, hirer)` primary key — one
payout per hirer per listing, ever. Plus a per-listing daily payout ceiling
(`MARKET_PAYOUTS_PER_LISTING_PER_DAY = 5`) so a crowd of throwaway accounts
can't farm one listing, and a progress gate (`highest_floor >= 5`) so
minutes-old accounts can't be payout mules. Re-hiring still *delivers* the
teacher (the client already paid locally) — it just never pays twice.

*Verified.* 10 repeat hires now mint one payout; fresh accounts get 403;
the daily ceiling holds against 9 fresh accounts; a legitimate first hire
still pays the lister exactly the listed price.

### HIGH — 5

**H1. No request body cap → unauthenticated memory-exhaustion DoS.**
FastAPI buffers the whole body before validation, so per-endpoint checks
(`MAX_TEAM_JSON_BYTES` etc.) ran far too late. A single unauthenticated POST
with a multi-hundred-MB body could OOM the container — which also takes down
the *other* app on that VM.
*Fix.* `BodySizeLimitMiddleware` (pure ASGI, 256 KB) rejects on
`Content-Length` and also counts streamed/chunked bodies, before parsing.
*Verified.* 400 KB body → `413`.

**H2. No rate limiting anywhere.** `/arena/challenge` and
`/arena/matchmake` each run a **full combat simulation** and move
ELO/wins/guild-war score. Unlimited, that's both a CPU tap on the shared
box and an infinite ladder farm (challenge the same weak opponent forever).
`/auth/register` allowed unlimited free accounts — the multiplier behind C1.
*Fix.* Sliding-window limiter keyed on real client IP *and* account:
auth 20/15 min, combat 30/10 min, market 20/10 min, writes 120/min.
*Verified.* 429s appear on login, register, and matchmake floods.

**H3. Login throttle was an account-lockout weapon.** The old logic locked a
*username* for 60s after 5 failures. Anyone could keep a known player
permanently locked out (5 wrong guesses a minute, forever) — a targeted
denial of service against a specific person. Meanwhile credential stuffing
*across* many usernames was completely unthrottled, since nothing counted
per-IP.
*Fix.* Per-IP limiting is now the brute-force ceiling; per-account failures
add friction (a tighter bucket) but never hard-lock. Added a constant-time
dummy bcrypt compare on account-miss so response timing no longer enumerates
valid usernames/emails.
*Verified.* Floods produce 429s while the victim's account still
authenticates; ≥15 of 30 attempts return 401 rather than a lockout.

**H4. Docker publish spec exposed the API around Caddy.** The documented run
command was `-p 8001:8001`, which binds `0.0.0.0` — and Docker writes its own
iptables DNAT rules that bypass ufw/firewalld. Port 8001 was therefore
plausibly reachable directly from the internet in cleartext, skipping Caddy's
TLS and any edge protection.
*Fix.* Documented command is now `-p 127.0.0.1:8001:8001`, with an explicit
external verification step. **Action for you:** confirm on the live box (§5).

**H5. Hostile hero snapshots reached the shared combat engine unvalidated.**
`combat.py` fed client dicts straight in via direct indexing (`h["health"]`,
`h["morale"]`), and client-supplied skill `actions` arrays were unbounded.
Consequences: `Infinity`/`NaN`/string stats and missing keys → 500s;
absurd magnitudes distorting every fight; and a real **amplification vector**
— a 64 KB team packing thousands of actions, each applied per cast per round,
inflating CPU and the *stored* combat log into tens of megabytes written to
`arena.db` and returned over the wire.
*Fix.* `security.clamp_hero_snapshot()` normalizes every submission: finite
numbers only, magnitudes bounded (`MAX_STAT`, `MAX_HEALTH`), ratios clamped
to 0–1, names/paths length-capped, portrait paths stripped of traversal and
URL schemes, skills capped at 12/hero and actions at 8/skill. It also
*guarantees* the fields the engine indexes directly, so a snapshot missing
`morale` can no longer 500.
*Verified.* 11 checks — clamping, coercion, `Infinity` neutralized,
traversal stripped, action arrays bounded, and the oversized variant dying at
the body cap.

### MEDIUM — 4

**M1. Session tokens stored in plaintext.** Any read of `arena.db` (backup,
volume snapshot) yielded every live session for its full 7-day life.
*Fix.* Stored as `v2:<sha256>`; the plaintext is returned once and never
persisted. Legacy plaintext rows are still accepted and upgraded in place, so
**no one gets signed out by this deploy**.
*Note on my own first attempt:* the migration path initially let a stolen
*hash* be replayed as a bearer token (a 64-hex digest is indistinguishable
from a 64-hex token). My test caught it; the `v2:` prefix plus a
`token NOT LIKE 'v2:%'` guard on the legacy lookup closes it.
*Verified.* Plaintext token works, DB holds only the digest, replaying the
stored digest → 401.

**M2. Local backend accepted drive-by cross-origin requests.** The local
game backend has no auth (correct — it's the player's own save), but CORS
does **not** stop a hostile page from *sending* a cross-origin POST; it only
stops it reading the response. So any website the player visited while the
game was running could blind-fire state changes at `localhost:8000` —
dismiss heroes, spend gold, wipe a permadeath roster.
*Fix.* Origin/Referer guard in `backend/main.py`: requests bearing a foreign
`Origin` (or foreign `Referer` on writes) get 403. Browsers can't forge
`Origin`; the webview, the dev server, and non-browser callers are unaffected.
*Verified.* Game/dev origins 200; `https://evil.example` 403 on GET, POST,
and Referer-only POST.

**M3. `CORS allow_origins=["*"]` on the world server.** Not CSRF (auth is a
Bearer header, not a cookie), but it let any web page freely script the API.
*Fix.* Closed by default; opt in via `ARENA_ALLOWED_ORIGINS`.

**M4. No security headers.** *Fix.* `SecurityHeadersMiddleware` adds
`nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, HSTS,
`Cache-Control: no-store`, and a CSP with `frame-ancestors 'none'`; strips
`Server`/`X-Powered-By`.

### LOW / accepted

- **L1.** `update_floor` is client-authoritative (clamped 1–1000). A modified
  client can claim floor 1000 → inflated PvE leaderboard + a one-shot burst
  of guild-war score. Throttled; not otherwise fixable without server-side
  simulation of the entire climb.
- **L2.** `reset_season` ranks by raw wins, which H2's fix now bounds.
- **L3.** Admin route returns 403 on a wrong key of any length (verified — no
  500 via `compare_digest` on mismatched input).

### Verified NOT vulnerable

Worth stating, since these are where vibecoded apps usually fail:

- **IDOR:** every read/write scopes by the authenticated username, not a
  client id. `claim_reward` (`WHERE id = ? AND username = ?`), `my_rewards`,
  `my_matches`, whisper threads (`sender = ? OR recipient = ?`), and guild
  actions (`_require_membership` + rank checks + cross-guild
  `app["guild_id"] != m["guild_id"]`) all check out. Tested: B cannot claim
  A's reward (404, stays unclaimed); A still can.
- **SQL injection:** every query is parameterized. No f-string SQL with user
  input.
- **Guild economy:** `guild_coin` is a proper server-side ledger with real
  deduction and weekly purchase caps — the correct pattern.
- **Chat abuse:** server-side slowmode + length caps; guild channel resolved
  server-side from membership (you can't post into someone else's guild).
- **SSRF:** no endpoint fetches a user-supplied URL.
- **Command injection / path traversal:** no `os.system`/`subprocess` on user
  input; no user-controlled file paths (portrait paths are now sanitized).
- **Secrets:** `.env` and `game.db` are gitignored; **the packaged
  `Giltgrave.exe` (formerly `Everspire.exe`, originally `InfiniteGacha.exe`) contains no API key** (verified by scanning the binary —
  `datas=[]` in the spec, and players enter their own key in-game).
- **Prompt injection:** LLM output is used only as flavor text (names, lore,
  narration) — it never drives a privileged action.
- **Combat loop safety:** fights are bounded (`max_rounds = 30`) and
  `resolve_targets` clamps target counts, so no infinite-loop hang.

---

## 3. What changed

| File | Change |
|---|---|
| `arena_server/security.py` | **New.** Rate limiter, body cap, security headers, XFF-aware client IP, token hashing, snapshot clamping. |
| `arena_server/main.py` | Middlewares; CORS closed; hashed tokens (+ legacy migration); IP/account throttles; constant-time login miss; login audit; `market/hire` rewrite; snapshot clamping on submit; legacy `/arena/login` routed through the hardened path (it had been minting plaintext tokens inline). |
| `arena_server/database.py` | `login_audit` + `market_hires` tables. |
| `arena_server/Dockerfile` | Localhost-only publish spec + verification steps; `--proxy-headers --forwarded-allow-ips`. |
| `arena_server/test_security.py` | **New.** 34 exploit-regression checks. |
| `backend/main.py` | Drive-by cross-origin guard; CORS list tightened. |
| `app_launcher.py` | Explicit `--host 127.0.0.1`. |

---

## 4. Residual risks / accepted tradeoffs

**Accepted — inherent to the design.**

1. **Arena stats are client-authoritative.** This server has no access to any
   save, so it cannot recompute what a hero *should* have. A modified client
   can field a stronger team than it owns. Snapshots are now clamped to
   plausible magnitudes, so the blast radius is "wins ladder matches it
   shouldn't" — not "hangs the server." Fixing this properly means the local
   backend signing snapshots (defeatable, since the client holds the key) or
   moving climb simulation server-side (a different game). **For a
   friends-scale ladder, accept it.** Revisit before anything competitive
   carries real stakes.
2. **The local save is player-editable.** Single-player, offline, on their
   machine — every offline game has this. Not worth defending.
3. **Rate limits are per-process and in-memory.** They reset on container
   restart and wouldn't span replicas. Correct tradeoff at this scale;
   revisit if you ever run more than one container.

**Worth doing before a wider launch.**

4. **Rotate `ANTHROPIC_API_KEY` anyway.** It isn't in the exe or in git, but
   it has been in a local `.env` across a long dev history — cheap insurance.
   The in-game key onboarding already means players use their own.
5. **Server-side validation for anything competitive.** If a real ranked
   season or paid rewards ever ride on ELO, snapshots need signing or
   simulation. Today's ladder is cosmetic.
6. **Persistent/edge rate limiting.** Caddy-level limits would blunt floods
   before they reach Python.
7. **Email verification.** Registration accepts any well-formed address, so
   one person can still make several accounts (now throttled per IP, and the
   payout paths are capped). Verification is the real fix if the economy ever
   depends on account uniqueness.
8. **`arena.db` file permissions** on the host volume (0600) — hardening the
   box, outside this review's scope.

---

## 5. Deploy checklist (not done — needs a container restart)

Nothing here has been deployed. When you're ready:

```bash
# 1. Rebuild (context must be the repo root — combat.py imports backend/)
docker build -f arena_server/Dockerfile -t tower-world-server .

# 2. Stop the old container, start with a LOCALHOST-ONLY publish
docker stop world-server && docker rm world-server
docker run -d --name world-server -p 127.0.0.1:8001:8001 \
  -e ARENA_ADMIN_KEY="<long random string>" \
  -v world_data:/app/data \
  tower-world-server

# 3. Verify from OUTSIDE the VM
curl -m 5 http://<public-ip>:8001/     # MUST fail — no direct exposure
curl -m 5 https://<caddy-host>/        # MUST return the status JSON
curl -sI https://<caddy-host>/ | grep -i -E "content-security|x-frame|strict-transport"
```

Existing sessions keep working (legacy tokens migrate on first use). No
client rebuild is required — no request/response shapes changed.
