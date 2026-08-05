# Giltgrave UI polish checklist
*2026-08-03. Written for a fresh Claude Code session to execute. Goal: raise
the "screenshot density" of the in-game menus without touching layouts or
systems. The diagnosis: the Illuminated identity is strong, but large
regions of pure black carry no texture, portraits are small relative to
text, and key frames are under-ornamented, so static captures read sparse.
This is a lighting-and-ornament pass only.*

Ground rules for the executing session:
- The design system lives in `frontend/src/index.css` (single stylesheet,
  the "ILLUMINATED KIT") plus primitives in
  `frontend/src/components/ilm/Ilm.jsx` and `Ornaments.jsx`.
  Read `design-handoff/README.md` first for the vocabulary, but trust the
  CODE for anything the handoff contradicts (the handoff predates the
  Giltgrave rename).
- Never introduce border-radius, emoji, or new fonts. Hard edges, notched
  corners, Cinzel/Cormorant only.
- Keep every change token-driven (use the existing CSS variables).
- Screenshot before/after at 1920x1080 for each item (the Playwright
  harness pattern from 08-03 works: offline sandbox copy of the save,
  localStorage tab_tour_complete=true).

## 1. Kill the dead black (highest impact)

- [ ] Combat stage (`.ilm-combat-stage`, index.css ~2125-2263, used by
      `components/CombatArena.jsx`): the battlefield between the two
      formations is near-pure black. Add a faint zone-art backdrop: the
      floor's environment image at very low opacity (8-14%) with a heavy
      dark vignette, or at minimum the Ornaments `starfield` scatter. The
      env images already exist (`frontend/public/images/floors/*.png`) and
      TowerPage knows the zone.
- [ ] Roster page body (`pages/HeroesPage.jsx`): the area behind the hero
      rows/tiles is flat. Bring the `Ornaments` component's `manuscript`
      variant up slightly in opacity behind the grid, or add the faint
      diagonal hairline pattern the landing page uses.
- [ ] Vault/inventory (`pages/InventoryPage.jsx`): same treatment.
- [ ] Modals (`.ilm-modal` family): the gradient (#160d27 to #0b0716) is
      good but interiors of large modals (hero detail at 1060px) have empty
      black wells. A whisper of the dot-scatter texture inside panels fixes
      the flatness.

## 2. Portrait presence

- [ ] Hero rows (HeroesPage list rows): the diamond portrait is small; the
      row reads as a spreadsheet line. Either enlarge the diamond by ~30%,
      or add a soft violet glow behind it (`box-shadow` with
      rgba(139,70,214,...)) so faces read at a glance.
- [ ] Combat formation cards: same; the unit diamonds should glow by team
      color when acting (the acting hero's card already animates, but the
      idle cards are flat).
- [ ] Hero detail modal (`components/HeroDetail.jsx`): the portrait should
      be the visual anchor. Consider a full-height cutout on one side
      (like the landing page hero art) when a cutout exists for the hero.

## 3. Frame ornamentation

- [ ] `.ilm-corner` gold L-ticks exist but are used sparsely. Add them to
      the four corners of: hero detail modal, summon result frames, the
      victory panel, and the profile card.
- [ ] Section headers inside pages (`.section-header`): the trailing
      hairline is 1px flat. Give major screens (Summon, Tower, Base) a
      double-rule with a center diamond, matching the landing page's
      tagline rules.
- [ ] The top bar (`components/ilm/TopBar.jsx`): currency chips and the
      wordmark are fine, but the bar bottom edge is a plain 1px border.
      A subtle gold gradient hairline (transparent-gold-transparent, like
      the landing tagline rules) makes every screenshot's top edge look
      finished.

## 4. Juice the money surfaces

- [ ] Card backs in the summon reveal (`components/SummoningOverlay.jsx`):
      currently flat dark rectangles with a name. This is the most
      screenshotted surface in any gacha. Give the face-down card an
      embossed diamond sigil, a faint radial sheen, and a slow shimmer
      (the landing page's slash-shimmer keyframe pattern works). Rarity
      glow may leak subtly from the edges BEFORE the flip for 5-star+
      (anticipation, like every major gacha).
- [ ] The reveal aura behind flipped 6/7-star cards is good; add the
      ember-rise particles (`ember-rise` keyframes already exist in
      index.css) behind 7-star flips.
- [ ] Victory banner (`.ilm-vic-slash`): add the gold hairline top/bottom
      borders the landing slash bands use; currently it floats on black.
- [ ] Floor event card (TowerPage `.ilm-floorevent`): frame it like an
      illuminated plate: corner ticks + a drop-cap on the first letter of
      the narrative (Cormorant has beautiful capitals; a CSS
      `::first-letter` at 3em in gold).

## 5. Micro-motion (only where it photographs well)

- [ ] Idle glow pulses on primary CTAs in-game (the landing `cta-glow`
      keyframe, applied to `.btn-gold`/`.ilm-btn-gold`).
- [ ] The gate rings on SummonPage already rite-spin; add a very slow
      counter-rotating inner ring for depth.
- [ ] Meters (`.ilm-meter` violet-to-gold ramp): a slow sheen sweep on
      full meters.

## 6. Verification pass

- [ ] Re-capture the 8 landing screenshots (ascent, reveal, fray, roster,
      explore, hero, base, gate) with the same Playwright flow and compare
      side by side with the 08-03 set in
      `arena_server/landing/assets/shots/`. The test: does each screen
      look "expensive" as a STILL, at a glance, to someone who has never
      played?
- [ ] Update the landing slider jpgs with the new captures and redeploy
      the world server (deploy/RUNBOOK.local.md flow).

Non-goals: no layout changes, no new screens, no color-token changes, no
scrollbars, no border-radius, nothing that alters game behavior.
