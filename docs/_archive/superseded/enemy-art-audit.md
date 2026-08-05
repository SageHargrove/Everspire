# Enemy art audit — Liam's verdicts (2026-07-06)

**EVERYTHING gets regenerated — none of the existing art is keeper/LoRA
quality (only heroes are).** The "liked" list below means the CONCEPT and
composition landed and should be *recreated better* with the new pipeline;
the unliked rest needs concept rethinking too. New-pipeline target: void
recipe (hero-style plain dark background, creature lit by its own glow,
species anchor, no scenes, no background sigils) for beasts; the
hero-grade HUMANOID_EVIL_STYLE for anything person-shaped. Only
new-pipeline renders the user approves go to confirmed/monsters
(currently just the r4 harpy).

## CONCEPT APPROVED — recreate better (liked)
- **Boss**: lich_king, the_stormcaller__sky_tyrant. *(all other bosses: redo)*
- **Elite** w1: all three (goblin_shaman, goblin_warrior, spider_queen) ·
  w2: ogre, troll (troll should be BIGGER/more intimidating) ·
  w3: hobgoblin_berserker, lizardman_stalker (close, could improve a bit) ·
  w5: minotaur_juggernaut, wyvern_stormrider ·
  w6: dread_brute, obsidian_behemoth, primordial_vampire (NOT stone_golem) ·
  w7: all — abyssal_lurker, frost_wight, shrouded_reaper ("he's sick") ·
  w8: black_knight_commander, hydra ·
  w10: adult_dragon, dracolich (NOT archdemon_enforcer).
  *(elite w4 plague_harbinger + scarab_swarmlord, w9 all: redo)*
- **Miniboss** (liked but want MORE DETAIL via new pipeline, and REMOVE the
  background symbols/magic circles): bullhorn_the_minotaur_lord, goblin_king,
  orc_warchief, skarn_the_lizard_chieftain, vaelor__the_fallen_ascendant.
  *(knight_captain_mordrek, pit_fiend_commander, stoneheart_the_unbroken,
  the_dracolich_herald, the_drowned_naga_queen: redo)*
- **Normal** w1: goblin only · w2: ALL six · w3: lizardman + hobgoblin
  (improvable but close; feral_ghoul: redo) · w4: bone_warden, grave_scarab ·
  w5: minotaur, manticore · w6: vampire_spawn · w7: naga + chimera (but
  "not sure the chimera is a chimera" — redo toward a real chimera) ·
  w8: giant (FACE needs improvement), hydra_spawn.
  *(w1 giant_spider+wolf, w3 feral_ghoul, w4 gargoyle/rotting_ghoul/wraith,
  w5 elemental/wyvern, w6 lesser_golem/stone_sentinel, w8 death_knight,
  w9 demon/imp, w10 all four: redo)*
- **Raid boss**: BOTH kept (aetherion, mordane).

## Special cases
- **Venom Stalker: ABANDONED as a concept** — three visual redesigns all
  failed. Replace the enemy concept itself (rename + new visual, the
  Slime→Shadow Wisp pattern). Touches combat_service ENEMY_TYPES + hints.
  Candidate replacement to pitch: a void-hound / gloom mastiff.
- Void-recipe verdicts so far: spider "okay", golem + serpent-hound bad.
  The void RECIPE is right (background-wise) but per-creature glow balance
  needs tuning — golem's molten glow swallowed the whole body.

## Regeneration campaign (next session)
1. Rewrite hints for every "redo" entry: void background, own-glow
   lighting, species anchor, no scene prose, no background sigils.
2. Humanoid-shaped redos go through HUMANOID_EVIL_STYLE.
3. Generate → Liam reviews → keepers to confirmed/monsters → repeat.
4. Improvement passes (regenerate, user compares against current): troll
   (bigger), elite w3 pair, normal lizardman/hobgoblin, minibosses (detail,
   no sigils), giant (face), chimera (actual chimera anatomy).
