# Stage 0 — memorial panel mockups

Three PNGs so the panels feature can be judged from pictures instead of from a
paragraph. **Nothing is wired into the game.** No schema change, no death-flow
hook, no frontend, no generation. If these don't look worth posting, the
feature dies here and the cost was an afternoon.

Regenerate with `python noobai-test/make_panel_mockups.py`.

| file | beat |
|---|---|
| `panel_1.png` | Who they were — full figure, unmodified, establishing |
| `panel_2.png` | The moment — silhouette, scale contrast, speed lines |
| `panel_3.png` | The memorial — she isn't in it |
| `strip_all_three.png` | All three stacked, as a reader would scroll them |

## What is real and what is faked

**Real** — every pixel:

- Hero: `noobai-test/validate_e10/3_7star_soraya.png`, the adopted hero LoRA's
  own output, cut out through `portrait_cache._border_flood_cutout` — the same
  function the game uses.
- Boss: `static/portraits/enemies/boss/boss_demon_overlord.png`.
- Scenery: `frontend/public/images/floors/`.
- Sword: `21_ornate_greatsword` from the equipment training set, chroma-keyed
  off its magenta plate and rotated upright.

**Real** — the string formats. Every quoted line uses the exact template
`deeds_service` / `legacy_service` emit:

```
"Cut down {n} foes in a single battle — floor {floor}"
"Refused to die on floor {floor}"
"The Weight {name} Carried"
```

**Faked** — the scenario. Soraya, floor 47, and the prose sentences after each
quote are written for the mockup. See the gap below for why they had to be.

## The thesis these images are testing

Panel variety comes from **framing, not from new drawings**. One hero image
carries all three panels: full figure, mirrored silhouette at a third the
scale, blurred ghost. Nothing was generated to make this, and nothing would be
generated per hero in the real thing either.

The alternative the addendum assumed — a sprite bank of 4 poses × 4 expressions
per hero at ~30s of GPU each — is unaffordable for a roster of disposable
heroes and re-opens character drift. What framing loses is action poses and
changing expressions. A eulogy needs neither.

## Gap found while building this

**A hero's death can never produce a Deed.** Two separate reasons in
`deeds_service.record_deeds`:

1. It returns `[]` immediately unless `result["winner"] == "heroes"`
   ([deeds_service.py:84](../backend/services/deeds_service.py#L84)). A party
   that wipes generates nothing for anyone.
2. Even in a win, six of the nine deed sources iterate `survivors`. A hero who
   dies in a *winning* fight can only earn a deed from the two sources that are
   specifically about not dying — Prophet's foresight and Undying Will.

So the most memorable deaths in the game produce no record at all, and the
final panel — the one that quotes how they went out — has nothing authentic to
draw from. That is why the scenario above is assembled rather than pulled from
a save: no save contains a hero who died and left a Deed, because the code
cannot produce one.

This is a design call, not a bug fix, so it hasn't been changed. Stage 1 needs
it decided either way: a `record_final_deed` path for the fallen, or panel 3
reads from the combat log's death line instead of from `hero_deeds`.
