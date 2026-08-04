# Landing page shot list

The landing page has a screenshot gallery ("FROM THE CLIMB") that is **hidden
until real captures exist**. Drop PNGs into
`arena_server/landing/assets/shots/` with the exact filenames below and the
section appears on its own — tiles whose file is missing remove themselves, so
partial coverage is fine. No HTML edits needed.

**Do not use the `design-handoff/screenshots/` mockups.** They still carry the
old `TOWER OF ETERNITY` wordmark and invented zone names ("The Ashen Court");
every capture must come from the live game.

## How to capture

- Run the game fullscreen at 1920x1080 (tiles render 16:9; anything close
  crops fine via `object-fit: cover`).
- Windows key + Shift + S -> full-screen snip, or Win+PrtScn.
- Use a real save with a leveled roster — empty UI reads as vaporware.
- Pick moments with gold/violet glow on screen; the page frame is dark, so
  bright UI moments pop.
- Optional: recompress before committing
  (`venv` python: `Image.open(p).save(p, optimize=True)`), or just keep each
  under ~500 KB.

## The seven slots

| filename | screen | stage it like this |
|---|---|---|
| `summon-reveal.png` | Summon reveal overlay | A 10-pull mid-reveal with at least one 6★/7★ frame visible (prismatic border is the money shot). Card-flip spin midway also works. **Wide tile — leads the gallery.** |
| `combat.png` | Tower combat (rank-list layout) | Mid-fight on a named zone floor with a skill-slash banner on screen (rotated violet band) and floating crit numbers. Elite or boss-phase fight preferred. |
| `tower-ascent.png` | Tower page | The zone climb path with several floor diamonds cleared and the zone rail visible — deep zone (VII+) so the floor count impresses. |
| `hero-detail.png` | Hero detail modal | A high-star hero with generated art, full mastery/branch panel visible. This is the "a hero of your own" proof shot — pick a portrait that isn't in the shared pool. |
| `base.png` | Home Base | Facilities view with upgraded (t3/t4) facility art cards showing. |
| `memorial.png` | The Memorial | ALL WHO FELL with a real casualty list. The permadeath receipt — arguably the most on-brand shot on the page. **Wide tile.** |
| `roster.png` | Heroes page | A full roster grid, mixed star tiers so the frame colors ladder (bronze -> gold -> prismatic). |

## Video (for a later pass — the page doesn't embed video yet)

Worth recording when convenient, in priority order:

1. A 10-pull reveal, uncut — flip anticipation into a 7★ rainbow.
2. One full floor of combat with a death -> the KIA banner -> the Death
   Ceremony ember screen. That 30-second arc IS the game's pitch.
3. Zone transition montage: 3-4 zones' backdrops, 2 seconds each.

Keep clips under 30 s. When the time comes, an autoplaying muted webm behind
the hero section is the obvious upgrade — ask for it and the slot gets built.
