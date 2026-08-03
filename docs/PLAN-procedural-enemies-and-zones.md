# Plan — per-player enemies and zones

Goal: two players who both start a tower should not meet the same five monsters
in the same five rooms. Overlap in *archetype* is fine and wanted — goblins,
skeletons and dragons are load-bearing fantasy furniture — but the specific
roster, its stat spread, its names, and the order of zones should be theirs.

**Nothing here is built.** Written while the art regeneration runs so it's ready
to start against a settled art pipeline.

---

## Why this is safe to automate

An enemy in this engine is not code. It is a 6-tuple plus a short ability list:

```python
("Goblin Warrior", 1.2, 1.1, 1.0, "elite", "beginner")
#  name            hp   atk  spd  archetype  tier
ENEMY_ABILITY_OVERRIDES["Goblin Warrior"] = ["cleave"]
```

- `archetype` ∈ `{swarm, normal, pack, elite}` — drives count and formation
- `tier` ∈ `{beginner, intermediate, advanced, …}` — gates which floors it spawns on
- abilities ⊆ `{cleave, enrage, summon_add, team_buff_aura, self_regen,
  crushing_blow, last_stand}` — **seven, total**

So the generator is only ever choosing from closed sets and setting three
numbers. **It cannot invent a mechanic**, because there is nowhere to put one.
Everything it returns is validated against the enums and the multipliers are
clamped; anything unrecognised is dropped, not passed through. That is the
whole reason this is a reasonable thing to hand to a model.

This is also not a new pattern here. `generate_boss_enemy(zone_theme, floor,
is_miniboss)` already returns exactly this shape of JSON, behind
`call_with_timeout(..., 1.5)` with a hardcoded fallback, and
`generate_zone_theme(start_floor)` already writes zone names and blurbs. This
extends a proven path rather than opening a new one.

---

## Schema

Per-profile, because that is the unit of uniqueness.

```sql
CREATE TABLE zone_roster (          -- which zones this player's tower has
  zone_index   INTEGER PRIMARY KEY, -- 0-9, floor N is zone (N-1)/10
  slug         TEXT NOT NULL,       -- picked from the floor-plate library
  name         TEXT NOT NULL,
  blurb        TEXT NOT NULL,
  band         TEXT NOT NULL        -- low | mid | high
);

CREATE TABLE custom_enemies (
  id           INTEGER PRIMARY KEY,
  zone_index   INTEGER NOT NULL,
  name         TEXT NOT NULL,
  hp_mult      REAL NOT NULL,       -- clamped 0.6-2.0
  atk_mult     REAL NOT NULL,       -- clamped 0.6-2.0
  spd_mult     REAL NOT NULL,       -- clamped 0.6-2.0
  archetype    TEXT NOT NULL,       -- validated against the enum
  tier         TEXT NOT NULL,
  abilities    TEXT NOT NULL,       -- JSON list, filtered to the known seven
  portrait     TEXT,                -- NULL until art lands; falls back meanwhile
  UNIQUE(zone_index, name)
);
```

`portrait` being nullable is the important part: an enemy is **playable the
instant it is generated**, using shipped art for its archetype, and its own
portrait swaps in later. Combat never waits on the GPU.

---

## Cold start

The problem: a player can be fighting on floor 1 within a minute of launching,
long before anything is tailored to them.

The answer is that **we never generate for the zone they are standing in**:

| when | what |
|---|---|
| first launch | zone 1 uses the **shipped** roster. Instant, no wait, no exceptions. |
| while in zone 1 (10 floors) | generate zone 2's roster + art in the background |
| while in zone N | generate zone N+1 |

A zone is ten floors. Five enemies is roughly two minutes of GPU on the
existing `PRIORITY_ENEMY` lane, which already sits below a hero the player is
actually looking at. The buffer is enormous. Only zone 1 is ever stock, and by
the time they leave it, everything ahead of them is theirs.

If generation is off entirely (no GPU, no key), every zone stays stock and the
game is exactly what it is today. This is strictly additive.

---

## Zone order

Zones are drawn per profile, not fixed — but drawn from **bands**, so the first
thing a new player sees is never Dragon's Boneyard:

| zone index | band | drawn from |
|---|---|---|
| 0-2 | low | caverns, ruins, swamps, badlands |
| 3-6 | mid | catacombs, peaks, crystal, drowned |
| 7-9 | high | rifts, boneyards, void, calderas |

The existing `tier` values on enemies (`beginner`/`intermediate`/`advanced`)
already encode this, so the band constraint is data we have rather than a new
concept to maintain.

**This is what the 40 generated floor plates are for.** Rather than replacing
the 11 zone plates, they become a library: each profile draws 10 band-
appropriate plates from 40+. That is real per-player variety at zero per-player
art cost, which is the cheapest uniqueness in the whole plan.

---

## Where the work actually is

Three things, in the order they should be built:

1. **Storage + generation** (backend only). The two tables above, a
   `generate_zone_enemies(zone_theme, band, count)` beside the existing boss
   generator, and hard validation. Testable without touching the UI.
2. **Art backfill.** Enqueue each new enemy's portrait at `PRIORITY_ENEMY`.
   Already has a lane, already has a fallback.
3. **Zone randomisation** (touches the frontend). `ZONES` is currently a
   hardcoded array in `TowerPage.jsx` and `zoneFor(floor/10)` indexes it, so
   zone identity has to move to profile data served by the backend. Last,
   because it is the only piece with a UI dependency.

---

## The real risk: art backlog, not generation

Generation is cheap — a roster is one LLM call. The GPU is the bottleneck, and
it is already serialised through one ComfyUI instance shared by:

- the ~27-portrait hero buffer (`MIN_PER_STAR`)
- every star-up re-render (urgent)
- now ~50 enemy portraits

On a weaker card the tail is long, and enemy art could lag a player who climbs
fast. Mitigations, both already patterns in the codebase:

- stay a **full zone ahead**, never generating for the current one
- **fall back to shipped enemy art** whenever `portrait IS NULL` — the same
  thing the hero pool does, and the reason `portrait` is nullable

What we should NOT do is block a fight on a portrait. A player who out-climbs
their art should see stock monsters with custom stats and names, not a
loading screen.

---

## Deliberately out of scope

- **LLM-authored abilities.** The seven are hand-tuned against the combat
  maths. A generated eighth would be untested and unbalanced by construction.
- **Per-enemy art for swarm trash.** A swarm spawns 5-8 identical units; giving
  each its own portrait is GPU spent where nobody looks.
- **Regenerating a player's roster.** Once a zone is theirs it stays theirs —
  the point is that it is *their* tower, and a reroll button undermines that.
