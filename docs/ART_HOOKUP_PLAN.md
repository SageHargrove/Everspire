# Art hook-up plan

State of each art category as of 2026-08-03, and what's left to do. Written so
this can be picked up cold in a later session.

Counts below were measured, not remembered. Anything I did not verify is marked
UNVERIFIED — check it before acting on it.

---

## Summary — UPDATED 2026-08-04

| category | art on disk | wired up | what's left |
|---|---|---|---|
| Floors / zones | 64 ✅ | ✅ **done** | nothing |
| Facilities | 73 ✅ | ✅ yes | nothing known |
| Monsters | **87/87** ✅ | ✅ yes | nothing |
| Heroes | 264 cutouts ✅ | ✅ yes | 147 legacy still in retired style |
| Equipment | 0 PNG / 12 sigils | partial | **generate art — LoRA now ships** |

Two alarms in the first draft of this document were WRONG and are corrected
below. Both came from counting with a glob that did not recurse.

- **"Elite tier is empty"** — false. All 29 elites have art; it lives in
  `elite/wave1..10/` subfolders, and `ls elite/*.png` does not see it. Enemy
  art is complete: 87 of 87 types. Verify with
  `python tools/gen_missing_enemies.py --dry-run`, which checks all three
  locations the game checks.
- **"base_pool/ is empty, may be broken again"** — false alarm. The pool reads
  `static/portraits/cutouts_heroes` (264 files, `DEFAULT_POOL_DIR` at
  `portrait_cache.py:929`). The empty `base_pool/` is vestigial.

---

## 1. Floors / zones — ART DONE, WIRING NOT

The library is finished: 64 plates in `frontend/public/images/floor_library/`,
all passing `tools/check_zone_plates.py`, each with an AI-authored name, tile
blurb and art prompt in `zones.json` beside them.

**None of it is reachable in game.** `ZONES` is still a hardcoded array at
`frontend/src/pages/TowerPage.jsx:89`, so every player walks the same ten zones
and the 64 plates are inert. This is the highest-value remaining task and it
gates the enemy-variety goal, because zones are what decide which enemies show
up.

What the wiring needs to do:

1. Draw 10 zones per profile from `zones.json`, banded — low covers floors
   1-30, mid 31-70, high 71+. Bands are already encoded in each filename as
   `band_slug.png`, so the draw needs no lookup table.
2. Seed the draw from the profile so a player's tower is stable across
   sessions — redrawing every load would make the tower feel unmoored.
3. Read name and blurb from the manifest rather than the hardcoded list.
4. Keep a fallback: if a slug in a save is missing from the library (art
   deleted, older save), fall back to a default plate rather than breaking the
   climb.

Also outstanding here: three low-band zones are apocalyptic and should not sit
on floors 1-30 — `charred_spinney`, `glassworks_deep`, `millstone_garden` are
burning lava fields. The plates are good, they're just filed wrong. Fix with:

    python tools/reband_zones.py --show
    python tools/reband_zones.py glassworks_deep=high millstone_garden=high charred_spinney=mid

That tool moves the file AND the manifest entry together, and validates the
whole batch before touching anything — band lives in two places and editing
either alone silently desyncs the library.

---

## 2. Facilities — LOOKS DONE

73 plates in `frontend/public/images/facilities/`, wired in
`frontend/src/pages/BasePage.jsx:50` as tiered art:
`/images/facilities/<slug>_t<1-4>.png`.

Nothing known outstanding. Worth one visual pass to confirm all four tiers
exist for every facility — 73 is not divisible by 4, so at least one facility
is missing a tier, or some are shared.

---

## 3. Monsters — ELITE TIER IS EMPTY

Measured in `backend/static/portraits/enemies/`:

    normal    15
    elite      0     <-- gap
    miniboss  12
    boss      23
    _old_scene_bg  22   (superseded style, not in use)

50 hooked up against a roster of roughly 90 enemy types. Two jobs:

1. **Fill the elite tier.** Zero art means elites are either falling back to
   normal art or rendering blank — confirm which before generating, since a
   silent fallback would look like it works.
2. **Close the roster gap.** ~40 enemy types have no art of their own.

Use `tools/regen_monsters.py`. Note from earlier work: monsters do NOT need
FaceDetailer (they're mostly non-humanoid, and it costs time for nothing), and
a bulk re-cut of monster cutouts previously made 110 of them *worse* — the tool
auto-reverts when the transparent-pixel ratio moves more than 1.5pp, so leave
that guard in place.

`_old_scene_bg` holds 22 plates in the retired style. Delete once the roster is
complete and nothing references them.

---

## 4. Heroes — VERIFY THE POOL SOURCE FIRST

Measured:

    cutouts_heroes  264
    masters         116
    cards            36
    base_pool         0     <-- empty
    offline           0     <-- empty
    confirmed         0

**`base_pool/` being empty is the thing to check first.** An earlier migration
commit shipped an empty hero pool once already (the directory was gitignored,
so `git add` refused silently while recording 147 deletions). Either the pool
reads from `cutouts_heroes/` instead and this is fine, or it's broken again.
Find out before generating anything — UNVERIFIED.

The authored roster is `backend/services/base_pool_characters.py`: 88
characters, 44/44 gender split, covering all 22 classes, with
`by_class_gender()`. Rebuild with `tools/build_base_pool.py`.

Second job: **147 legacy heroes are still in the retired manhwa style.** They
predate the migration to `Everspire_Heroes_v1` and need regenerating to match.
This is the largest single GPU job left.

Star-up art is settled and needs no further work: 4★ and 7★ milestones,
img2img at denoise 0.72 unweighted, `_tier_flavor(star)` applied. Per-star
escalation was tested and abandoned — img2img can't repaint gear without
repainting the face, and inpainting produced seam artifacts.

---

## 5. Equipment — GENERATE ART (decided 2026-08-04)

Decided: equipment gets real art, not sigils. Sigils stay for drops and
consumables, where the roster is large and each item is small. Equipment is
personal and worth the pixels.

`Everspire_Equipment_v1` exists and was trained alongside the others. It had
never been shipped — it was in the local ComfyUI only, absent from
`generation/loras/`, `INSTALL_GENERATION.bat` and `generation_installer.py`.
Fixed on 2026-08-04, along with `Everspire_Floors_v1`, which had the same
problem. Equipment art would have rendered as the base model for every player
while looking correct on the dev machine.

Remaining work:

1. Confirm the roster size (~134) and where equipment art is displayed.
2. Generate at 1024x1024 with `Everspire_Equipment_v1`, magenta chroma key —
   a black key does not work, since much equipment is itself dark.
3. `tools/gen_equipment_sample.py` generated an 8-icon comparison earlier;
   look at it before committing to the full run.
4. Wire the display path. `frontend/public/icons/equip/` currently holds 12
   SVG sigils — decide whether art replaces them or sits alongside for large
   displays only.

### Superseded reasoning (kept so it isn't re-litigated)

Measured: **0 PNGs**, 12 SVG sigils in `frontend/public/icons/equip/`.

Do not start generating 134 equipment PNGs without settling this first. The
standing art doctrine is that icon-scale art is **sigils only** and AI-generated
icon PNGs were retired — small AI icons read as mush below about 48px. A bulk
equipment PNG run would directly contradict that.

So the real task is a decision:

- **Sigils** — consistent with doctrine, cheap, scales to any roster size, but
  12 sigils against ~134 items means many items share a mark.
- **Art** — only defensible if equipment is displayed large somewhere (a detail
  panel, not a grid slot). An 8-icon comparison sample was generated earlier to
  test exactly this; find it and look before deciding.

Once decided, the count to fill is the roster size, not 12.

---

## Suggested order

1. **Reband the three low-band lava zones** — one command, thirty seconds.
2. **Wire the zone draw** — unlocks all 64 plates and the enemy-variety work.
   Frontend + save-format change, no GPU.
3. **Verify the hero pool source** — cheap check, and it's the failure that has
   already bitten once.
4. **Fill the elite monster tier** — GPU, smallest of the generation jobs.
5. **Regenerate the 147 legacy heroes** — GPU, largest job, run it overnight.
6. **Decide equipment sigil-vs-art** — needs your eye, not compute.

---

## Operational notes

- Release the GPU with `powershell -File tools/stop_generation.ps1` when done.
  `pkill` and `ps -W | grep` both fail silently on this machine, and ComfyUI
  holds ~7GB VRAM after a script exits — "generation stopped" is not the same
  as "GPU released".
- `tools/check_zone_plates.py` flags plates too dark to work behind hero
  cutouts. Thresholds are calibrated against real output; intuition-set ones
  flagged 19 of 44 and were useless.
- When a generated batch comes out samey, check the PROMPTS before blaming the
  model. Four separate collapses this round were all upstream in the text:
  prompt length, water, violet, and explicitly named darkness. And do not fix
  them by listing alternatives — enumerating options in a prompt that runs 44
  times installs a new default (banning violet while suggesting "rust" put
  "rust" in 44 of 44 prompts). Rotate one assignment per item instead, the way
  `SPATIAL_TYPES` and `PALETTES` do in `backend/services/llm_service.py`.
