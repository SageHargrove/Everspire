# Giltgrave Depth Roadmap
*2026-08-03 — consolidated from the systems audit, Liam's decisions, and the
manhwa/retention research. This is the plan of record for strategy depth and
floor-50+ retention. Nothing here is implemented yet except the bug fix noted.*

## Decisions already made (Liam, 08-03)

- **Combat stays autobattler.** The player is the Master, not the pilot. No
  skill-priority programming, no mid-fight input. Depth comes from WHO you
  field, WHERE they stand, and WHAT you learned about the floor.
- **No position-restricted skills** — especially with grid formations coming.
- **Formations are the approved combat-depth axis** (see below).
- Hero-management proposals approved: bond slots, mentorship-as-assignment,
  legacy pedestals, ego defiance.
- Facility A/B specializations + Wall rework approved.
- Economy diversification approved.
- Rejected (standing, from content roadmap): battle orders, ascended reruns,
  combat pet, nemesis mechanics. Floor 100 stays brutally far.

## Bug status

- **FIXED (08-03): `CLASS_EVOLUTIONS` duplicate keys** in
  `backend/services/class_service.py`. Seven profession lineages were defined
  twice; the dead first copies (pre-support-revamp trees) are removed.
  Behavior unchanged — 19 base classes, 148 reachable names. The retired
  names (War Master, Void Walker, Head Chef, etc.) are listed in a comment if
  ever wanted back.
- **PLANNED: merge the two environment systems.** `combat_service.
  FLOOR_CONDITIONS` (28%/floor, 6 conditions) and `environment_service.
  ZONE_CONDITIONS`+`HAZARDS` (always-on per band) overlap and can stack in
  one fight; several effects are symmetric and decision-neutral. Not a
  hot-fix — merging changes balance. Do it as part of Formations/Intel work:
  one system, every condition asymmetric and counterplayable, surfaced in the
  floor preview so scouting reads it.

---

## 1. Formations (combat depth, approved direction)

Today: order-only — `frontline = team[:2]`, index-matched targeting. One
solved decision.

**Target: saved formations on a grid.**

- A team owns up to N **formation plans** (start: 3). Each is a placement of
  its 5 heroes on a small grid — recommend **3 columns x 3 rows** (front /
  mid / rear), max 2 per row-position, empty cells allowed.
- Player either picks a **preset** (Phalanx 3-front, Standard 2-front,
  Turtle 1-front, Skirmish wide, Ambush rear-heavy) or drags their own.
- Pre-fight, choose which plan to deploy (or set per-floor-type defaults:
  "vs boss use Turtle, vs swarm use Phalanx"). That's the manager decision;
  the fight still runs itself.
- Mechanics the grid feeds (no per-skill position restrictions):
  - **Row semantics**: front row draws fire first; rear row is safer but
    Assassin-type enemies and `isolated` targeting reach it. Column overlap
    determines cleave/AoE spread.
  - **Width tradeoff**: wider front = damage spread thinner but cleave hits
    more; narrow front = focused tanking but Unimber-style lone-target
    penalties threaten.
  - Enemy formations get the same grid, shown in the floor preview for
    visited floors — formation choice becomes the scouting payoff.
- Engine changes are modest: replace the `[:2]` split with grid lookups in
  targeting/cleave; formation JSON on the team row; preset library; UI on the
  existing FORMATION button (drag heroes on a 3x3).

## 2. Hero management

- **Bond slots**: cap *active* bonds per hero (e.g. 3). Bonds beyond the cap
  exist but give no stat bonus until slotted. Breaking an active bond (or a
  partner dying) costs morale/grief. Choosing WHOSE +% you keep becomes a
  real pick, and squads that always climb together stay strong.
- **Mentorship as an assignment**: mentoring occupies the mentor like a
  facility slot does (UNIQUE assignment already exists — extend the same
  table with an `assignment_type`). Your best teacher can't also staff the
  Forge or climb. Keep the 2.5x `teaching_multiplier` ladder.
- **Hall of Remembrance (legacy pedestals)**: sacrifice legacies no longer
  stack unboundedly. The Memorial gains 3-5 pedestals (scaling with facility
  level); only enshrined legacies are active. Choosing whose memory fights
  with you gives sacrifice permanent weight — and revisiting the Memorial
  becomes gameplay.
- **Ego defiance**: when a hero's patience breaks, offer a choice instead of
  auto-compliance: *yield* (accept their team edit, +harmony) or *defy*
  (hero gains a "Defiant" state — small self-buff, squad-wide morale risk,
  chance to refuse orders). Complying stops being strictly correct.

## 3. Facilities

- **A/B specializations at levels 10 / 25 / 40** per facility, mutually
  exclusive, respec only via a costly rite. Examples:
  - Forge: *Volume* (cheaper, faster crafts) vs *Masterwork* (+rarity-roll
    chance, slower)
  - Athenaeum: *Breadth* (2 nodes studied at once, slower each) vs *Depth*
    (+insight rate, single node)
  - Tavern: *Rowdy* (more morale, stress risk) vs *Reverent* (less morale,
    trauma healing)
  - Infirmary: *Triage* (faster recovery) vs *Sanctuary* (trauma ceiling
    repair)
  Two players' bases should read differently by mid-game, like the
  confluence fork already does.
- **Wall permits**: each Wall level grants K foundation permits; upgrading a
  facility past certain tiers consumes one. The Wall stops being "always max
  first" and becomes a budget you allocate.
- **Second workers matter**: `_resolve_supports` currently uses only the
  best-mastery assignee. Give additional assignees a minor additive
  contribution (e.g. +10% of their mastery value) so staffing depth is real.

## 4. Economy

- **Smuggler's rotation**: Market gains a rotating stock (3-day cycle, seeded)
  with limited quantities — occasional rare materials, odd equipment, one-off
  curiosities. Buy-now-or-wait decisions; Smuggler discount finally shines.
- **One deliberate exchange**: aether <-> materials at an unfavorable, slowly
  improving rate (Merchant-lineage assignment improves it). Surpluses become
  decisions, not dead ends.
- **Keep no-high-pity as stated identity** ("the Gate owes you nothing — the
  Spark ledger is your contract"), but consider PMU-style **achievement-gated
  guarantees**: first-clear of each zone's boss grants a Spark bundle or a
  one-time guaranteed-4★ ticket with provenance ("from the Floor 20 dragon").
  Deterministic, earned, non-purchasable.
- Equipment: break the "higher grade is always right" scalar — give set
  families and weapon types distinct stat *shapes* at equal grade so affinity
  choices bite.

## 5. Floor-50 retention program ("the wall is a mountain, not a meter")

Research guardrails (full reports in the 08-03 session): progress must
**ratchet** (failure costs only the attempt), difficulty must be **chosen and
legible**, meta-currency must **widen options, not refill stats**, no daily
chores, never punish absence. At the wall a player should answer "what am I
building toward my next attempt?" and "what here is mine?" — never "what do I
owe the game today?"

Build order (extensions of shipped systems first):

1. **Wall Sentinels + Intel (the spine).** Every 10th floor from 50 is a
   *named* Sentinel with hidden mechanics. Scouting attempts and wipes accrue
   **Intel** into its bestiary page (moveset reveals, weakness entries,
   phase order). Intel thresholds unlock Sentinel-specific Athenaeum research
   and Training Grounds **drills** that grant heroes a persistent Insight
   trait against that Sentinel family. PMU parallels: replay stones, the
   Wailing Wall's ordered-objective solution. Failure literally pays.
2. **Insight currency** binding it: earned from bestiary completion, scouting,
   mastery grades; spent ONLY on knowledge (pre-reveal a floor's deal, reroll
   a dealt floor, unlock drills, pre-identify affixes). Never buys stats.
3. **Zone Mastery**: per-zone grade tracks (speed / no-death / full-bestiary)
   on already-cleared zones paying wall-prep materials. Player-composed, not
   re-tuned content (respects the no-ascended-reruns rejection).
4. **Echoes of the Fallen**: a qualified fallen hero leaves an Echo at the
   Memorial. Echoes can be bequeathed to a successor (fragment trait + a
   chronicle line: "carries Serane's vow"); visiting the Memorial before a
   declared wall attempt grants a named blessing from your specific dead.
5. **Risk Contracts**: compose elite-affix + environment modifiers onto
   cleared zones for a legible risk score; rewards are seals, titles, and an
   Insight trickle. (Arknights CC / Hades Heat shape.)
6. **Master Fame**: world-server rankings on multiple axes (deepest, zero-
   death, lowest-rarity clear, risk score, bestiary %) + profile-card titles
   + a Herald bulletin for server-first Sentinel breaks. Reputation, not
   nemesis.
7. **Bond vignettes**: bond levels + deeds unlock tavern scenes about who a
   hero was before the Gate. No power, just chronicle + tiny ego shifts —
   the login reason that isn't a chore.
8. **The Gauntlet**: periodic multi-wing challenge requiring 3 squads with
   per-hero lockout (roster width as the horizontal axis; reuse raid wings).
9. **Guild sieges on Sentinels**: pooled guild Intel ledgers, first-break
   banners recorded permanently, Intel inheritance as member catch-up.
10. Later / bigger: rift floors (one-shot twist vignettes found while
    farming), patron sponsorships (feat-style wishes layered on Deeds),
    seasonal fresh-roster pilgrimage (knowledge is all that carries over).

## 6. What the landing page advertises (already live 08-03)

"FOR THE CLIMBERS": seeded floors + scouting, talent-outranks-rarity +
Mirror of Fate, Spark wishlist as the Gate's contract, multi-team walls.
Challenge hook: "The Tower is undefeated. No one has seen the hundredth
floor. Climb anyway." As Sentinels/Intel ship, the page's strategy section
should grow to match.

## 7. Player-to-player: trading, visibility, and art portability

*Raised by Liam 08-03 while settling the sigil-vs-generated-art question.
NOT approved for implementation — this is the problem statement and the
recommended shape, to be decided before any of it is built.*

**The problem.** Giltgrave generates its content per player, locally: heroes
(stats via local `random`, prose via the Anthropic API, portrait via local
ComfyUI/GPU), equipment (rolled at drop time), floors and facilities. Every
cross-player feature needs that locally-made content to become *portable*.

### 7a. What actually exists today (audited 08-03)

Cross-player is **substantially real, not mocked** — more real than the UI
copy suggests:

- `arena_server/` is a live FastAPI+SQLite world server: auth, ELO duels,
  matchmaking, guilds, chat, raids, tournaments.
- It stores **full hero snapshots**, not aggregates — name, class, every
  stat, skills, aptitudes, `portrait_path` (`arena_server/security.py:288-342`).
- PvP opponents are **always real remote players**; there is no bot/fake
  opponent generator anywhere (`main.py:529-650`, `combat.py:82-89`).
- **Heroes already transfer between players.** Raid victors capture a hero
  from the loser and `integrate_prisoner` INSERTs that foreign hero into the
  winner's save (`backend/routers/raid.py:259-312`), carrying name, backstory,
  portrait_path, stats, skills, plus a `rebellion`/`original_master` mechanic.
- The **Training Market** is real and server-backed (`arena_server/main.py:1364-1474`):
  you list a hero as a *teacher*, buyers gain stats/skill XP locally, the
  teacher never leaves your roster. Knowledge, not property.
- **Item/equipment trading does not exist at all** — zero equipment code in
  `arena_server`. The `trade` chat channel (`arena_server/chat.py`) is an
  unenforceable bulletin board. `.ilm-market-row` is dead CSS.
- Equipment effects are **baked into the stat numbers** before submission
  (`combat_service.py:1811 resolve_hero_stats`), so item identity is already
  lost across the wire.

**Trust model:** every stat is a client-computed snapshot; the server
validates shape and magnitude but never recomputes — explicitly accepted for
"friends-scale v1."

### 7b. LIVE BUG — cross-player portraits 404 today

This is not a future concern; it is shipping now. `portrait_path` crosses the
wire as a **bare relative path** and is resolved against *the viewer's own*
backend. When you fight, scout, or capture a hero whose portrait was
generated on the owner's GPU (`static/portraits/<Profile>/alive/...`), your
client requests a file you don't have → 404, silently swallowed by `onError`
handlers (`CombatArena.jsx:224`, `HeroCard.jsx:524`). **Only heroes still on
shipped-pool/default art render correctly cross-player.**

It persists into permanent state: `integrate_prisoner` writes the foreign
path straight into your `heroes` table (`raid.py:277, 285`), so a captured
hero keeps a permanently-broken portrait reference forever.

### 7c. Art portability — and the precedent already in the repo

Two candidate models:

- **Model A — deterministic regeneration** (ship a seed, regenerate locally).
  *Rejected as primary:* needs bit-identical model + LoRA versions on both
  machines (they will drift), takes minutes rather than being instant, and a
  recipient **without an NVIDIA GPU cannot regenerate at all** — the API-key
  path is text-only. Worse, there is currently **no seed to ship**: heroes and
  equipment are rolled from unseeded `random` (§7e), so nothing is
  reproducible even in principle without adding seeds first.
- **Model B — content-addressed upload.** The owner uploads the finished PNG
  keyed by sha256 when it first becomes visible to others; others fetch by
  hash. Dedupe is free (shipped-pool art uploads once globally). Instant,
  GPU-independent. **Recommended.**

**The precedent already works in-repo:** the Banner Studio ships player-drawn
art cross-player *today* by embedding bytes rather than a path — a canvas
data-URL up to 400 KB in `banner_json` (`arena_server/main.py:871`), rendered
by other clients in `Pennant.jsx:61-64`. It works precisely because it is not
a path. Portraits need the same treatment, but by hash + fetch rather than
inline bytes (a portrait per hero per player is far too heavy to inline).

`arena_server` today has **no upload endpoint, no blob storage, no CDN** —
its only static mount is the marketing site (`main.py:245-246`). That is the
gap to close.

#### Why this does NOT mean "every player downloads every player's art"

The intuition that 100 players × 100 rosters = unusable bloat is the right
instinct, and it's what a naive "sync everything" design would do. Four
mechanisms keep it small, and they compound:

1. **Lazy fetch — you only ever pull what you actually look at.** Nobody
   downloads a roster. A portrait is fetched at the moment it appears on
   screen: the 5 heroes of the opponent you're fighting, the defenders in a
   scout report, a prisoner you captured. A heavy session might surface a few
   dozen images, not thousands. This is exactly how a browser loads a page.
2. **Content-addressing makes caching permanent.** A URL like
   `/art/<sha256>.webp` can never change content, so it's served
   `Cache-Control: immutable, max-age=1y`. You fetch any given portrait
   **once, ever** — re-fights, rematches and re-scouts cost zero bytes.
3. **Shipped-pool art dedupes to zero.** Most heroes use art that ships with
   the game. Same bytes → same hash → the file is *already on the viewer's
   disk*, so it never transfers at all. Only genuinely custom
   GPU-generated portraits are unique, and only those move.
4. **Bound what is shareable.** A hero only needs to be visible if the player
   *put it in front of others*: the arena attack team (5), the defense team
   (5), the profile-card face (1), market listings. That's ~10 heroes per
   player, not 30+. Everything else never leaves the machine.

**The actual arithmetic** (measured 08-03: full portraits are ~350-400 KB as
PNG, ~130 KB as mini; call it ~150 KB re-encoded to WebP):

- Server total, 100 players × ~10 shareable heroes × 150 KB ≈ **150 MB**.
  Even the pessimistic "every hero of every player" case is ~450 MB. The
  Oracle box absorbs either without noticing.
- Client cache, a heavy month of 20 arena fights × 5 enemy heroes ≈ 100
  portraits ≈ **15 MB**, fetched once and cached forever. Bound it with an
  LRU cap if desired.

Note the local `static/portraits` tree is currently ~5.6 GB / 2163 files, but
that is overwhelmingly staging, LoRA packages and enemy art — the
*shareable* surface is a tiny fraction of it, and should be explicitly
enumerated rather than "whatever is in the folder."

**Cheapest possible v1, if hosting is unwanted:** don't share custom
portraits at all — make the cross-player fallback explicit and graceful
(shipped-pool art, then sigil) instead of a silent 404. Zero infrastructure,
and it's honest. The cost is that other players see a generic version of your
hero, which undercuts "your heroes are yours." Recommended only as a stopgap
while the art endpoint is built.

**Render fallback ladder** (this is why the sigil doctrine matters — it is
the layer that makes this degrade gracefully instead of showing holes):
uploaded art by hash → local shipped-pool art → **house sigil**.

### 7d. What would have to move, by category

Split every item's **identity** (stats/mechanics — must be authoritative and
portable) from its **appearance** (heavy, optional, cacheable):

- **Materials + consumables** — fixed catalogs (~33 crafting materials across
  4 tiers in `materials_service.py`, plus ~30 consumables/gifts/tickets),
  fungible, and everyone renders the *same sigil locally*. **Zero art
  transfer.** Easiest possible trade target; ship first purely to prove the
  ownership-transfer plumbing.
- **Equipment** — procedurally rolled from **unseeded** `random` at drop time
  (`equipment_service.py:281-355`), with **no seed, no `catalog_id`, no
  `template_id`** anywhere on the table. The autoincrement `id` is local to
  one save file, so an item is **literally unreproducible** on another
  machine — there is nothing to reproduce it from. Any equipment trading must
  therefore move the **whole rolled stat block** as the item's identity, under
  a server-issued id. The *type* still renders locally as a sigil, so no art
  moves. Note the interaction: giving every equipment instance its own
  generated image would make every trade drag an image with it and break the
  "one sigil, recolored by rarity" model — trading is an independent argument
  for the 08-03 sigil decision.
- **Heroes** — already moving between players via raid capture (§7a), which
  is exactly why §7b is a live bug rather than a hypothetical. Text (name,
  backstory) already transfers fine; only the portrait is broken.

### 7e. Authority — the blocking constraint for *item* trading

Arena's client-authoritative snapshots are a standing accepted tradeoff for
stats: a cheater inflates their own numbers and wins fights they shouldn't.
That tradeoff **must not** extend to tradeable items. A client-authoritative
tradeable item is a duplication exploit with extra steps — the same class as
the 07-12 infinite-gem exploit, but permanent and economy-wide once items are
fungible between players.

So item trading forces the first genuinely **server-authoritative**
subsystem: tradeable items exist as rows on the world server with a
server-issued id and an `owner` column, and a trade is an ownership transfer
inside one transaction. The local save becomes a cache of "what the server
says I own" for those items only. **This is the real cost of trading — not
the UI.** It is also why materials should go first: same plumbing, lowest
stakes if it goes wrong.

### 7f. Moderation (gating requirement, not a nice-to-have)

The moment player-generated portraits are visible to other players, the game
is **publishing user-generated images**. Before any hero visibility ships it
needs, at minimum: explicit per-player opt-in to share art, a report path,
and an automated NSFW gate before an upload is served to anyone else. This is
a safety and legal exposure question, not an engineering detail — it should
gate the feature, not follow it.

### 7g. Open design question — a hero *market*?

Heroes already move between players **by conquest** (raid capture), which is
thematically consistent with permadeath and the Tower's cruelty — you take a
hero, they carry `original_master` and can rebel. That is earned, and it
should stay.

A hero **market** is a different thing, and the recommendation is **no**:
permadeath and the bond with heroes *you* summoned are the emotional core
(and what the landing page sells). A shop turns an irreplaceable loss into a
shopping trip. Capture keeps the stakes; a market removes them.

Proposed split: heroes transfer only by **conquest**, and are otherwise
**viewable** (profile card, arena opponent, guild roster); equipment and
materials become tradeable.

### 7h. Suggested sequencing

1. **Fix §7b first** — cross-player portraits are broken *today* and every
   new visibility feature makes it more visible. Minimum viable: a
   content-addressed art endpoint on `arena_server` + upload-on-first-share,
   with the sigil fallback ladder underneath.
2. Materials/consumables trading (catalog-only; no art problem at all) — to
   prove the server-authoritative ownership transfer at low stakes.
3. Equipment trading (whole rolled stat block under a server-issued id).
4. Broader read-only hero visibility, behind the §7f moderation gate.
5. Hero market — recommend never; see §7g.

### 7i. Unrelated bugs surfaced by the same audit (not yet fixed)

- **`frontend/src/api/arenaServerClient.js:111`** — `'\arena\claim_reward'`
  uses backslashes; `\a`/`\c` aren't valid escapes so the path collapses to
  the literal `arenaclaim_reward` with no leading slash. **Season reward
  claiming can never reach `/arena/claim_reward`** (`main.py:982`). Every
  neighbouring line uses forward slashes correctly. One-character-class fix.
- **`ArenaPage.jsx:487`** — "BASE RAIDS · COMING SOON" is stale copy sitting
  over a **fully live** feature (real scout/attack endpoints via
  `FeatureModals.jsx:209-228`). Also ":490 PREVIEW A SCOUT REPORT" for what
  is a real, gold-charging scout. Product-copy decision, so left alone.
- `gacha.py:58` comment says "once Gemini responds"; provider is Anthropic.
  `ArenaPage.jsx:36-37` claims no match-history endpoint, but
  `/arena/my_matches` exists. Both harmless stale comments.

### 7j. Seeds — worth adding SOON, independent of trading

Heroes and equipment are currently rolled from the **module-level** `random`
with no seed recorded, so nothing that has ever been generated can be
reproduced. Adding seeds is cheap now and **impossible retroactively** —
every hero and item rolled before the column exists can never have one. That
asymmetry is the whole argument for doing it early even though nothing
depends on it yet.

What it buys, in rough order of value:

- **Recreating a specific hero** — the "I want that one back" / showcase /
  seasonal-rerun case Liam raised.
- **Debugging and testing**: reproduce a reported roll exactly; write
  deterministic tests over generation instead of statistical ones.
- **Sharing a build as data** — a hero definition becomes a short string
  rather than a blob, useful for bug reports and community sharing.
- A *partial* art path: `portrait_prompt` is already stored (`gacha.py:433`);
  a seed alongside it makes regeneration far closer to deterministic.

**Implementation note — it is not just adding a column.** Determinism
requires replacing module-level `random.*` calls with an *instance*
(`rng = random.Random(seed)`) threaded through generation, in at least
`gacha_service.generate_base_stats/generate_aptitudes`, `assign_class`,
`assign_initial_skills`, `generate_traits`, and
`equipment_service` (`:281-355`, `:744-749`). Do it in one pass or the seed
records a lie.

**Honest limitation:** a seed reproduces a roll only under the *same
generation code and the same RNG call order*. Any balance change or reordered
call breaks old seeds. So seeds are a recreation/debugging aid, **not** a
substitute for shipping bytes cross-player, and not an archival guarantee.
Store a `gen_version` alongside the seed so a stale pair is detectable rather
than silently wrong.

## 8. Item taxonomy — how to get "a LOT of items" from ~20 sigils

Liam wants many distinct items: tiered potions (lesser/medium/greater, health
*and* mana), many mob drops, many ores. The 08-03 art doctrine says
icon-scale art is house line-sigils, not generated art
(see the art-scale memory / `EquipmentTypeIcon.jsx`). Those two goals are
compatible because a sigil is not one icon per item — it is **three
independent axes**:

**GLYPH (the noun) × COLOR (tier/quality) × MODIFIER (sub-tier)**

- **Glyph** = what kind of thing it is. One SVG, reused forever.
- **Color** = quality/tier, driven by the existing D→Z rarity palette. Free:
  sigils are CSS-mask recolorable, so `Iron Ore` and `Mithril` are the *same
  glyph* in two colors.
- **Modifier** = a small in-glyph variation for ordered sub-tiers — the
  cleanest being **fill level** (a flask drawn ⅓ / ⅔ / full).

Worked example — potions. Three fill-level flask sigils
(`FLASK_LESSER`/`_MEDIUM`/`_GREATER`), recolored green for health and blue
for mana, already yields **6 items from 3 SVGs** — and adds a 4th tier or a
whole new potion line (stamina, antidote, elixir) for one more SVG or zero.

Worked example — mob drops. Archetype glyphs (bone, fang, horn, talon, claw,
scale, hide, pelt, feather, chitin, ichor-vial, eye, sinew, trophy-ear) ×
tier color covers a very large drop table: the ~33 materials currently in
`materials_service.py` collapse to roughly a dozen glyphs, and the table can
grow to 100+ named drops without a single new SVG.

**Estimated set to cover everything today: ~20 SVGs.**
~12 material/drop archetypes + ~8 consumable glyphs (flask ×3 fill, meal,
bandage, charm, crate, whetstone). Compare ~63 current item names, or a LoRA.

**These are hand-authorable, not generated.** The existing sigils are plain
24×24 paths — `fill:none; stroke:currentColor; stroke-width:1.4;
stroke-linecap:round` (see `public/icons/status/BLEED.svg`,
`public/icons/equip/RING.svg`). No GPU, no LoRA, no generation queue. New set
would live at `public/icons/material/*.svg` (that directory does not exist
yet) and render through the existing `Sigil` component.

**Consequence for the LoRA plan:** skip a materials/consumables LoRA and
spend that GPU time on monsters, floors and facilities, which render large
and are genuinely unique. Keep the summon-ticket art — it survives icon scale
because it is a flat silhouette, and it is a "money object" the player stops
to look at.

---

# Combat presentation — battlefield layout and log placement

_Added 2026-08-04. Decisions taken with Liam; the alternatives are recorded so
they are not re-litigated._

## The problem

Enemy art renders at roughly 40px of actual creature inside a ~75px cell. The
90-odd monster portraits — each one a full generation pass, now on their own
trained LoRA — are effectively invisible in the one screen where they matter.
The zone backdrop has the same problem: 64 plates were built for the tower, and
the combat view occludes most of each one behind unit cards.

**The cause is NOT grid density.** It is the card chrome. Each unit sits in a
frame with a border, a fill, a name plate and an HP bar, and that furniture
consumes most of the cell. Shrinking the grid without removing the frame just
gives you bigger frames.

## Decisions

**Battlefield: 3x3 per side, cardless.** Units render as bare transparent
cutouts standing directly on the zone backdrop. A thin HP bar sits under the
feet; the name appears on hover or when targeted, not permanently. Expected art
size ~130-150px tall, roughly 3x today.

Rejected — **5x5**: 25 slots per side is more tactical depth than the roster
supports, and the cells come out ~40% narrower, landing art back near its
current size. It would have spent the whole layout change without fixing the
thing that prompted it.

Rejected — **keep the rank-list, drop the cards**: the cheapest option and it
does help (~100-110px), but it keeps the four-column structure that splits the
backdrop into strips. The backdrop only reads as a place when it is one
continuous surface.

**Combat log: right side rail.** Fixed-width column beside the battlefield,
full height, ~15 lines visible against ~4 today.

Rejected — **taller log below**: directly fights the battlefield for vertical
space, which is the axis the art needs.
Rejected — **translucent overlay on the art**: costs no layout space but text
over illustration is the hardest legibility problem in the UI, and this log is
read continuously during a fight rather than glanced at.

## Consequences worth flagging before implementation

1. **Formation semantics change.** Today's REAR GUARD / VANGUARD / FRONT LINE /
   BACK LINE columns carry real combat meaning. A 3x3 has to map onto that —
   most likely rows become the ranks (row 1 = front, row 3 = rear) — or the
   combat rules need revisiting. This is not a pure view change; check
   `combat_service` before touching `TowerPage`.
2. **Cutout quality becomes visible.** At 40px a ragged alpha edge is invisible;
   at 150px it is not. The dark-on-dark trims already known on the drake's
   wings and the harpy will show. Budget a cutout review pass alongside this.
3. **Portrait resolution.** Enemy art generates at 832x1216 and is displayed far
   smaller today. At 3x the display size the source is still sufficient — no
   regeneration needed for scale alone.
4. **Nine slots per side is more than the roster fills.** Most floors field 3-6
   enemies. Empty cells must read as intentional space, not as missing content,
   or the battlefield looks broken on light floors.
