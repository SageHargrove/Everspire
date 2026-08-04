# Giltgrave

A roguelike tower-climbing gacha RPG. You are the manager. Heroes die permanently.

Summon heroes, send them up an endless Tower floor by floor, manage a home base
between climbs, and watch combat resolve as a deterministic simulation —
positioning, gear, class synergy, morale, and a hero's personality (their
"Ego") all matter, and a bad floor can permanently lose you a hero.

---

## Playtest — Send This to Friends

**To play (no Python, no coding, nothing to configure):**

1. Download **`Giltgrave-Setup.exe`** from the [Releases](../../releases) page.
2. Run it. Windows will warn that it's unsigned: **More info → Run anyway**.
   (Signing costs a few hundred a year; this is a playtest.) It installs
   per-user — **no admin rights, no UAC prompt** — and makes Start Menu and
   desktop shortcuts.
3. Launch **Giltgrave** from the Start Menu or desktop.
4. At the title screen, **make an account** — please use a **throwaway
   password**, not one you use elsewhere. Multiplayer connects automatically.

There's also a plain **`Giltgrave-playtest.zip`** if you'd rather not install
anything: extract the whole folder and run `Giltgrave.exe` from inside it.

That's it. You play on the built-in art, and everyone shares one world server.

**Optional — better text.** Hero names, backstories, and banter are written by
Claude. Without a key you get pre-written text instead; everything else is
identical. To turn it on, paste an [Anthropic API key](https://console.anthropic.com)
into **Settings → AI**. It's stored locally and only ever sent to Anthropic.

**Optional — your own unique hero art (needs an NVIDIA GPU, ~12GB free disk):**

1. Run **`INSTALL_GENERATION.bat`** once — downloads ComfyUI, the art model,
   and the game's style LoRAs (~9GB, resume-safe if interrupted).
2. Start the game and switch ON **Hero Portrait Generation** under
   **Settings → AI**. Summons now roll heroes nobody else will ever have.

The generator starts and stops with the game from then on. No NVIDIA GPU? Skip
it — nothing else changes.

**Updating.** Saves live in `backend/saves/` and generated art in
`backend/static/portraits/`. Extract a new build over the old folder and keep
those two; everything else is replaceable.

---

## Building the Player Download

```bash
cd frontend && npm run build && cd ..                      # UI must be current
backend\venv\Scripts\python -m PyInstaller Giltgrave.spec --noconfirm
backend\venv\Scripts\python tools\make_release.py          # -> stage + .zip
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" tools\everspire.iss   # -> Setup.exe
```

That produces `release/Giltgrave/` (~1.1GB), `release/Giltgrave-playtest.zip`
(993MB) and `release/Giltgrave-Setup.exe` (923MB) — upload the last two to the
Releases page. Note the **module form** (`python -m PyInstaller`) — the
`pyinstaller.exe` shim in the venv hardcodes the pre-rename interpreter path and
fails silently with exit 1.

The installer is **per-user by design** (`PrivilegesRequired=lowest`,
`{autopf}` → `%LOCALAPPDATA%\Programs\Giltgrave`). That's not just to dodge the
UAC prompt: the game keeps saves and generated portraits *next to itself*, and
a Program Files install would put those in a directory the player can't write
to. Uninstalling removes everything the installer laid down and deliberately
leaves save data behind, so reinstalling picks a roster back up.

Two deliberate choices in that layout:

- **The exe stays small (~160MB) and game content sits *beside* it**, not frozen
  inside. That's what makes an update a drop-in replace of `Giltgrave.exe` +
  `_internal/` while a player's saves and generated portraits survive.
- **`make_release.py` picks backend files via `git ls-files`**, so gitignored
  things — `backend/.env` above all — cannot reach a release by accident. It
  also refuses to zip a stage folder that's been launched (a smoke-test run
  leaves a save DB and a WebView2 profile behind).

Because the backend is loaded as loose source rather than frozen, PyInstaller
can't see its imports: every third-party module it touches is declared by hand
in `Giltgrave.spec`. A `ModuleNotFoundError` in the packaged build almost always
means adding a package there — `collect_submodules`, not a bare name, for
anything imported as `pkg.sub`.

---

## Running It (Development)

`app_launcher.py` is the one-step launcher and runs in two modes from the same
file. From source it git-pulls, rebuilds the frontend, and starts uvicorn as a
subprocess out of `backend/venv`:

```
python app_launcher.py
```

Frozen (the build players download) it does none of that — there's no git
checkout, no Node, and no venv on a player's machine — and instead imports the
backend and runs uvicorn **in-process**. It no longer launches ComfyUI itself
either; the backend does that on startup via `comfy_service.ensure_comfy_running()`,
which honours the `COMFYUI_DIR` that `INSTALL_GENERATION.bat` sets.

`PLAY.bat` is still there as the bare-bones path (venv bootstrap + uvicorn, no
window) if you want the game in a normal browser tab.

The backend serves the frontend's built `dist/` directly, so if you've
changed any frontend code, rebuild it first:

```
cd frontend
npm run build
```

**For active frontend development** (live reload instead of rebuilding
every change), run the Vite dev server separately instead of relying on
the built `dist/`:

```
# Terminal 1 — Backend
cd backend
venv\Scripts\activate
python -m uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend (hot reload)
cd frontend
npm run dev
```

ComfyUI is only needed for generating new hero/enemy portraits — the game
runs fine without it, portraits just won't regenerate.

Save data lives in `backend/saves/<profile>.db` (git-ignored — one SQLite
file per profile). DB schema migrations run automatically at startup.

---

## How to Play

1. **Summon** → pull heroes and equipment with gold (standard) or gems
   (premium — better odds, builds Sparks toward a guaranteed 5★). Pulls
   reveal as face-down tarot cards — rarity-tiered card backs, click to
   flip (10-pulls deal all ten in a 3-4-3 spread over a summoning array).
2. **Heroes** → review stats, classes, aptitudes, Egos, skills (5-tier
   class-specific active/passive kits), traits, and weapon/armor affinity;
   set your teams (5 per team), pin favorites (♥ tab), compare any two
   heroes side by side, and give **gifts** — every hero secretly loves
   some gifts and resents others; loved gifts permanently raise a stat
   and build affinity (a 0-100 loyalty track).
3. **Synthesis Chamber** → sacrifice up to 3 heroes to feed another XP
   (doubled on matching-class Ego Resonance, with a chance to inherit
   skills/traits). The whole living roster witnesses the rite — trauma,
   stress, and morale loss compound with every additional soul consumed.
4. **Tower** → advance floor by floor — combat, events (narrative choices,
   sometimes turning into real fights), explore, escort, survival, ambush,
   blitz, and more. Every 5th floor is a miniboss comp-check (survival /
   behemoth / assassin / twins), every 10th a boss with real phases: wound
   one past two-thirds and again past a third of its health and it changes
   the fight. Combat resolves automatically; deaths are permanent and leave
   a Legacy bonus. Floor type stays hidden (?) until you've visited it once —
   after that, what you learned about it (condition, elite, boss phases) is
   remembered.
5. **Items (Vault)** → equipment (weapons — Sword/Spear/Tome/Bow/Dagger;
   armor — Robe/Light/Brigandine/Heavy; accessories — Ring/Amulet/Charm,
   with **two** accessory slots per hero), each type with its own stat
   identity and class-restricted equip. Storage is capped — build/upgrade
   the Vault facility to expand it. Consumables (potions, scrolls, summon
   tickets) are used from here.
6. **Base** → between climbs: assign heroes to Facilities (you start with
   the Wall, Training Grounds, and Dining Hall; everything else — Farm,
   Market, Forge, Infirmary, up through the floor-75 Transcendence Core —
   is built with gold, all core facilities unlocked by floor 25), cook
   Farm ingredients into consumables, refine Aether ship fuel, rest the
   roster, design your Team Banner, and read the Hero Chatter log / Lore
   Journal. Station a support-class hero in their own facility and their
   **Company Boon** rides along on every climb — a Chef's feast, a Medic's
   field surgery, a Tactician's opening gambit; which boon depends on the
   evolution branch they took, and its strength on their star and growth.
   Several facilities also open a hands-on minigame (forge timing, sigil
   tracing, a strategy board against a hero) that can multiply the result —
   always skippable, with the auto-resolve as the baseline. The Wall is the
   foundation: no facility can be upgraded above its level. In the Base
   Hierarchy, every hero lives on a base floor (Floor 1 by default; a new
   floor unlocks every 10 Tower floors) — spreading them out trades a
   bigger stat bonus per hero against coverage.
7. **World** → everything multiplayer: PvP arena against snapshot teams,
   PvP/PvE leaderboards, guilds (roster, shop, daily boss, chat, weekly
   wars), base raids, server-wide tournaments, and a training market. The
   game auto-connects to the World server (address:
   `DEFAULT_ARENA_SERVER_URL` in `frontend/src/api/arenaServerClient.js`).
8. **Achievements** → milestones across Tower/Summoning/Roster/Combat/
   Economy/Equipment/Arena, with a Claim All button. Rewards are gems and,
   for the hardest, star-tiered Summon Tickets — consumables (Items tab)
   that guarantee a 4★+/5★+/6★+/7★+ hero pull.

Heroes also accumulate **Deeds** — permanent one-line records of what they
actually did ("Felled the Hollow King", "Refused to die on floor 47"). Deeds
outlive the hero: the Memorial keeps them. The in-game **Codex** works the
same way, unlocking a page the first time you meet the thing it describes.

---

## Hosting Your Own World Server

The World server (`arena_server/`) is a separate FastAPI service that owns
accounts, PvP/ELO, guilds, chat, raids, tournaments, and the training market.
It never touches any player's local save. Self-hosting it:

```bash
# Build from the REPO ROOT — the image needs the sibling backend/ package
# for the shared combat engine.
docker build -f arena_server/Dockerfile -t tower-world-server .

# Publish to LOCALHOST ONLY and put a TLS reverse proxy (Caddy, nginx) in
# front. A bare `-p 8001:8001` binds every interface, and Docker's iptables
# rules bypass ufw — that exposes the API directly, in cleartext.
docker run -d --name world-server --restart unless-stopped \
  -p 127.0.0.1:8001:8001 \
  -e ARENA_ADMIN_KEY="<long random string>" \
  -v world_data:/app/data \
  tower-world-server
```

Then point `DEFAULT_ARENA_SERVER_URL` in
`frontend/src/api/arenaServerClient.js` at your public hostname and rebuild
the frontend.

Environment variables:

| Variable | Purpose |
|---|---|
| `ARENA_ADMIN_KEY` | Enables admin routes (season reset). Unset = admin routes disabled entirely. |
| `ARENA_DB_PATH` | Where `arena.db` lives (defaults to `/app/data/arena.db` in the image). |
| `ARENA_ALLOWED_ORIGINS` | Comma-separated CORS allowlist. Empty (default) blocks browser cross-origin calls; the game client doesn't need it. |
| `ARENA_TRUST_PROXY` | `0` disables `X-Forwarded-For` parsing for direct-exposure setups. Default trusts it, but only from a private/loopback peer. |

Security posture, threat model, and the hardening applied are documented in
[`docs/SECURITY.md`](docs/SECURITY.md). Regression tests:

```bash
cd arena_server && python test_security.py
```

---

## Repository Layout

```
app_launcher.py               # The launcher — dev mode (subprocess) + frozen mode (in-process)
Giltgrave.spec                    # PyInstaller onedir build; deps declared by hand
tools/make_release.py         # Assembles + zips release/Giltgrave/ for the Releases page
PLAY.bat                      # Bare-bones path — venv bootstrap + game at localhost:8000
INSTALL_GENERATION.bat        # Optional: local AI hero generation (NVIDIA GPU)
generation/loras/             # Hero style models (git LFS) pulled by the installer
Dockerfile                    # Container build for the single-player backend
docs/                         # Design/plan documents + SECURITY.md
openspec/                     # Feature specs (openspec workflow) + backlog

backend/
  main.py                     # FastAPI app, CORS, serves frontend dist/ + static assets
  database.py                 # SQLite schema + startup migrations, per-profile saves
  services/                   # Game logic — combat, gacha, classes, egos, legacies,
                              #   equipment (weapon/armor/accessory type identities),
                              #   facilities, support boons, materials, level/ascension,
                              #   skills, morale, deeds, events, LLM flavor text,
                              #   portrait generation
  routers/                    # API endpoints — heroes, gacha, tower, base, runs,
                              #   equipment, relics, crafting, arena, profiles, chat
  scripts/                    # One-off/maintenance scripts (icon generation,
                              #   card regeneration, db patches)
  tests/                      # Test scripts
  static/icons/               # Equipment art (weapons/armor, rarity-tiered)
  static/portraits/           # Hero/enemy/boss art (git-ignored, locally generated)
  saves/                      # Per-profile save DBs (git-ignored)

frontend/src/
  App.jsx                     # Tab layout, onboarding tour, resource header
  api/client.js               # All API calls (+ arenaServerClient.js for PvP)
  components/                 # HeroCard, SynthesisChamber, CompareModal, DialogHost,
                              #   Sigil, CombatArena, Codex, Tip, overlays...
  components/minigames/       # Facility minigames + the shared difficulty shell
  pages/                      # Summon, Heroes, Tower, Base, Arena, Achievements,
                              #   Inventory (Vault), Log
frontend/public/icons/        # UI icon art (currencies, classes, floors, status, boons)

arena_server/                 # The World server — see "Hosting Your Own World
                              #   Server" above. security.py holds the rate
                              #   limiter, body caps, and input clamping;
                              #   test_security.py is the exploit-regression suite.
```

---

## Known Gaps

- **Enemy roster art** — every enemy has art, but some of the harder monsters
  are placeholder-quality, and the Hydra family (Hydra, Hydra Spawn, Wyvern
  Stormrider, and the Hydra Sovereign boss) is temporarily cut from the roster
  pending a stronger monster art model (`ToE_Monsters_v2`, to be trained).
- **Arena stats are client-authoritative** — the World server has no access to
  any player's save, so it cannot recompute hero stats and a modified client
  can field a stronger team than it owns. Submissions are clamped to plausible
  magnitudes so the blast radius stays "wins ladder matches it shouldn't."
  Accepted for a friends-scale ladder; see `docs/SECURITY.md`.

## Roadmap (working as designed, not gaps)

- **Personal generation** — local hero generation works today for NVIDIA-GPU
  players (`INSTALL_GENERATION.bat`), toggled on by entering any API key. A
  hosted path — so players *without* a GPU can pay for their own renders via a
  real API key — is future work, not built.
- **Summon Tickets** — fully working (`/gacha/use-ticket`, tier art 4★–7★).
  Deliberately super-rare; surfaced through Achievements now, and event rewards
  once events ship.
