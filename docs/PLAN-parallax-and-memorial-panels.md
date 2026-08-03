# Plan — Parallax Cards & Memorial Panels

Two features, deliberately sequenced so the cheap certain one ships first and
the expensive uncertain one has to earn its place.

## Status

- **Feature A, parallax — BUILT.** `components/ParallaxCard.jsx` + the
  parallax block in `index.css`, wired into `CardFrame`. Frontend only,
  reverts by deleting one component and one CSS block.
  Standalone demo: `docs/parallax-demo/index.html` (opens from disk).
- **Feature B, panels — STAGE 0 DONE, awaiting the call.** Three mockups in
  `docs/panel-mockups/`. Nothing wired into the game. Read that folder's
  README before deciding — it documents a real gap in the deed data these
  panels would read from.

---

## Feature A — Parallax hero cards

Tilt-on-pointer depth effect on hero cards. Layers at different Z under a
perspective transform; move them at different rates as the pointer crosses.

**Why it's first:** pure frontend, no backend, no generation, no pipeline
change, no interaction with anything else in this document. It cannot break
the game and it makes every screenshot better — which, per the launch plan, is
the marketing.

### Scope
- 3–4 layers per card: background plate, hero cutout, frame/nameplate, and a
  light sweep.
- Displacement stays small — **3–8px equivalent**. Nobody has ever complained
  a card's parallax was too subtle; they complain when it warps.
- Pointer on desktop, `deviceorientation` on mobile, both clamped.
- Respect `prefers-reduced-motion` — this is exactly the kind of effect that
  makes some people ill.

### How it was built

`ParallaxCard` publishes two unitless CSS variables on its own node, `--px`
and `--py` in [-1, 1], and CSS does every pixel of the motion. No React state
changes while the pointer moves — the roster renders 24 cards at once and a
setState per mousemove is a stutter machine. The rect is cached on
`pointerenter` rather than measured per move, and writes are batched into one
`requestAnimationFrame`.

**Only the framed art tilts; the name and stats below it stay flat.** The card
reads as a still page with a window cut into it rather than a slab being
skewed — and it keeps clear of `.hero-card:hover`, which already owns a
transform on the outer card.

Details that turned out to matter:

- **Not clipped.** `.card-frame-banner` ("KILLED IN ACTION") is drawn at
  `left/right: -8%` on purpose; an `overflow: hidden` would slice its ends off.
  Layer travel is capped low enough that the spill is invisible.
- **`will-change` only while active.** Permanent promotion on 24 cards is 24
  compositor layers of GPU memory bought for nothing.
- **Touch uses `deviceorientation`, not the pointer.** A finger is *on* the
  card, so tracking it would hide the art under the hand. One shared window
  listener for the page, not one per card. iOS needs a permission prompt from
  inside a user gesture, which a card can't ask for — there it stays flat.
- **Dead heroes don't tilt.** They're dimmed to 40% and aren't clickable;
  a jaunty shine on a corpse is the wrong note.
- `prefers-reduced-motion` is checked both at the event level and in a media
  query, so flipping the OS setting mid-session goes flat immediately.

Actual cost: a few hours, not the 2–4 days estimated.

---

## Feature B — Memorial panels

When a hero dies, produce a 3-panel comic page about *that hero*, from the
record the game already keeps.

### The insight that makes it affordable

The original addendum assumed panel variety needs a **sprite bank** — 4 poses ×
4 expressions per hero, generated at ~30s each. For a roster of disposable
heroes that is not affordable, and it re-opens the character-consistency
problem.

It isn't needed. Panel variety in comics comes from **framing**, not from new
drawings. From one existing cutout, with zero generation:

| Shot | Transform |
|---|---|
| Face close-up | crop head region, scale up |
| Mid-shot | crop torso-up |
| Small against a vast room | scale down, place low |
| Seen from behind | mirror horizontally, darken toward silhouette |
| Backlit in a doorway | tint to black, rim glow behind |
| Danger beat | red wash, raised contrast, tilted frame |

Six distinct panels, one asset, already cut out with alpha. What's lost is
action poses and changing expressions — neither of which a *memorial* needs.
A eulogy is contemplative by nature.

**Explicitly rejected: using the portrait as an img2img/IPAdapter reference to
generate panels.** That walks straight back into character drift at ~30s of GPU
per panel. Compositing is instant, free, deterministic, and identical every
time.

---

## STAGE 0 — Visual proof (do this first, decide from it)

**Goal: PNGs on disk that Liam can open and judge. No game integration, no
frontend work, no schema changes. A throwaway script.**

### What it does
1. Pull a **real** dead hero from a save — name, class, star, floor, portrait
   path, and their rows from `hero_deeds` and `legacies`.
2. Load their **real** cutout from `static/portraits/.../cutouts_heroes` (or a
   profile's `alive/` dir).
3. Composite 3 panels with PIL at 800×1280 each (webtoon slice spec):

```
PANEL 1 — WHO THEY WERE
  background : a quiet interior plate
  hero       : full figure, centred, unmodified
  text       : caption from their earliest Deed

PANEL 2 — THE MOMENT
  background : the floor/zone plate where they died
  hero       : mirrored, darkened toward silhouette, small, low-left
  antagonist : the boss/elite sprite from static/portraits/enemies, large,
               right, darker still
  fx         : red wash + radial speed lines
  text       : bubble + caption from the death event

PANEL 3 — THE MEMORIAL
  background : dark starfield plate
  prop       : planted-sword memorial asset — no figure at all
  text       : name, class, star, floor range, final Deed, Legacy line
```

4. Write them to `docs/panel-mockups/` and stop.

### Deliberately excluded from Stage 0
- Any frontend rendering
- Any new generation
- Any DB writes
- Any hook into the death flow

### Assets Stage 0 needs
- **3 background plates.** Generate with the environmental/floors LoRA once
  those finish training, or hand-pick 3 existing floor images. Not per-hero —
  these are shared.
- **1 memorial prop** (planted sword). One image, shared forever.
- Everything else already exists.

### The decision gate
Look at the three PNGs. **If they don't read as something worth posting, the
feature dies here** and the cost was an afternoon. If they do, Stage 1 starts
with the layout already validated.

### Stage 0 result

Built and rendered — `docs/panel-mockups/`, regenerate with
`python noobai-test/make_panel_mockups.py`. Every asset is real (hero from the
adopted LoRA, boss and floor plates from the game, memorial sword from the
equipment training set); every quoted line uses the exact `deeds_service` /
`legacy_service` template. Only the *scenario* is assembled.

**It had to be assembled, and that's the finding: a hero's death can never
produce a Deed.** `record_deeds` returns `[]` unless the party won
([deeds_service.py:84](../backend/services/deeds_service.py#L84)), and six of
its nine sources iterate `survivors` — so a hero who dies in a *winning* fight
can only earn a deed from the two sources specifically about not dying
(Prophet's foresight, Undying Will). The most memorable deaths in the game
leave no record, which is exactly the material panel 3 wants to quote.

Stage 1 can't start without deciding this:
- **(a)** add a `record_final_deed` path that fires for the fallen regardless
  of `winner` — changes the deed economy, needs its own thresholds; or
- **(b)** leave `hero_deeds` alone and have panel 3 read the combat log's death
  line instead. Cheaper, no economy change, but the Memorial page still shows
  nothing for a hero who died on a losing floor.

---

## STAGE 1 — Real implementation (only if Stage 0 passes)

### Text — templated, never generated
Steal Wildermyth's markup: `<hero>`, `<hero.mf:He/She>`, personality-conditional
branches. Zero AI, zero latency, zero moderation surface, works for players with
no API key — which is most of them.

Sources already in the DB:
- `hero_deeds` — the beats, including the base-life and chained-smith deeds
  added this session
- `legacies` — title and flavour text, `is_sacrifice` for the rarer wording
- `hero_bonds` — who to name as the mourner
- the combat log's death line — how they actually died

An LLM caption pass is possible later but must stay **optional and cached**,
never on the critical path.

### Backgrounds
15–25 plates covering the zone bands, plus memorial/base plates. Generated
offline with the floors LoRA, hand-culled, shipped with the game. Shared across
all players — this is not per-hero art.

### Where it hooks
`combat_reveal_service` already defers deaths for dramatic timing, so the
panel generates at the same moment the death is revealed. The Memorial page
gets a "view page" button per fallen hero.

### Speech bubbles
Trivial here and hard elsewhere: the compositor **placed** the sprite, so the
head coordinate is already known. Point the tail at it. No face detection.

### Estimate
**2–3 weeks** after Stage 0, most of it background authoring and 2D layout,
very little ML.

---

## Sequencing

1. **Stage 0 mockups** — one afternoon, decides everything
2. **Parallax** — 2–4 days, independent, ship regardless
3. **Panels** — only on a yes from Stage 0

## Explicitly NOT doing

- **Gear compositing.** Requires every hero locked to one pose, which
  contradicts the pose variety deliberately added to the generation prompts.
  Varied poses were chosen; this is the cost.
- **3D / full 360° heroes.** Thin features (blades, hair, cape edges) are the
  universal failure mode of image-to-3D and they're what these heroes are made
  of. Parallax delivers most of the felt effect for ~2% of the work.
- **Runtime panel generation.** Keeps Steam AI disclosure at Tier 1 (a checkbox
  and a sentence) rather than Tier 2 (dedicated store section, documented
  models, heavier review).
