# Giltgrave strategic-depth audit (code-verified)
*2026-08-03. Every claim read from backend/services unless noted. Format per
system: what exists, what to ADVERTISE, where it's THIN.*

## 1. Combat (combat_service.py, environment_service.py, skill_engine.py)

Exists:
- Fully auto-resolved server-side; frontend replays at x1/x2/x4. All
  decisions are pre-fight.
- Formation is order-only: `frontline = team[:2]`, index-matched targeting.
  Assassin-class enemies hit the backline; taunt/escort/runner override.
- Damage: endurance mitigation with armor-pen, brace x1.6 def, morale under
  40 scales damage to as low as 0.5x, variance 0.85-1.15, crit x1.8,
  isolation +30% taken. Basic attacks always use STR; INT classes live
  through skills.
- Mana: 20 + 4xINT + 2xWIL; attackers gain 5/hit, defenders 8 (tanks
  generate more, deliberately). Skill choice is first-castable-in-list-order.
- Statuses: bleed/burn/poison (poison stacks), stun, freeze, taunt, blind
  (60% miss), silence, disarm, shields, regen, stat mods.
- Bosses: shell_armor (70% reduction until 4 hits), summons, auras, revive,
  cleave, enrage, crushing blow, last stand. Phases at 66%/33% HP (walls at
  50/70/90 add a 15% phase): harden, ritual (heals AND cleanses DoTs),
  quicken, shed_armor (def halved, STR x1.6), fury, cataclysm.
- Elite affixes: Armored, Frenzied, Colossal, Deadly, Regenerating, Warded
  (+40% magic resist); second stacked affix past floor 80.
- TWO overlapping environment layers (floor conditions 28%/floor, severity
  doubles past 60; zone conditions always-on per band; hazards like rising
  tide that compound per round).
- Panic system: base chance by star (20% at 1-star to 2.5% at 7), shaped by
  talent, willpower, tendency; Reckless/Glory-Seeking panic INTO isolation,
  others brace. Bond grief on ally death; ego resentment can make a hero
  refuse to fight.
- Death saves: Prophet foresee, then Oracle death_save charges (cap 2),
  then permanent death.
- Minibosses that check comps: Behemoth (DPS check), Assassin (backline
  check), TWINS (60% phys-resist twin + 60% magic-resist twin: mono-damage
  comps cannot brute-force), Mirror (clones your team). Objective floors:
  survival, escort, retrieval, blitz.
- Floors are SEEDED: composition, condition, affix, boss phases derive from
  floor number. `/tower/floor/preview/{n}` reveals them for visited floors.

Advertise: seeded floors + scouting loop; Twins/Mirror comp checks and the
phase library; panic/tendency as a build axis; leader doctrine (below).

Thin: no in-fight agency at all (fine, chosen); skill priority is list
order with NO player reorder (rejected as depth lever: stays autobattler);
formation is one solved decision (FIX: grid formations, see roadmap);
consumables auto-fire at fixed thresholds; the two environment systems
overlap and half the effects are symmetric no-ops decision-wise; elite
affixes have no counterplay hooks surfaced.

## 2. Hero management

Exists:
- Talent: 5 aptitudes, growth multiplier 0.5x-3.0x, extra skill slots from
  talent. A high-talent 1-star promoted up grows like a natural 7-star (this
  is IN the code comments). Mirror of Fate sells the info in 3 detail tiers
  (word / range / exact) priced star x500 gold; reveal freezes at building
  level at time of purchase.
- Star caps 10/20/40/60/80/99/120 (+5 per ascension). Evolution choice is
  BLOCKING at 30/60 (XP banks, level holds).
- 19 lineages, 148 reachable class names after the 08-03 dedupe fix.
  Profession branches: only specific evolutions (Butcher, Poisoner,
  Smuggler line, Beast Tamer line) ever fight; Blacksmith/Quartermaster/
  Priest lineages never do. Evolving an Alchemist to Poisoner permanently
  converts an economy hero into a fighter.
- Synthesis: XP by sacrifice star/level; same-class doubles it (Resonant
  ego); 50% inheritance roll per sacrifice; trauma to every living witness,
  escalating in mass rites; favorites are blocked as fodder.
- Legacies: qualification bar (level 30+ / 10 floors / mentorships); ONLY
  sacrificed heroes grant the stat bonus; specials for 20+ kills, 30+
  floors, 70+ trauma. Currently stack unbounded (FIX: pedestals).
- Mentors: level gap 8, 5-min cooldown, teaching multiplier to 2.5x
  (leadership/diligence aptitudes + mentors_heart). Currently free (FIX:
  assignment cost).
- Bonds: +1% four stats per total bond level with teammates; pure upside
  (FIX: bond slots).
- Egos: five types with team-shape demands (Resonant wants mono-class,
  Tactical wants 2/3 split); patience decay, conflict multipliers; at zero
  the hero rearranges your team (FIX: defiance choice).
- Loyalty/trust: survived +1, barely +2, deaths -3, wipe -5.
- Traits: weighted by star (30% negative at low stars, 5% at high);
  immutable; some PvP-only.

Advertise: talent-over-rarity + Mirror; synthesis resonance + trauma bill +
sacrifice-only legacies (a complete moral economy); the profession fork.

## 3. Facilities

Exists: 21 facilities, exponential gold ladder to level 50, gated by The
Wall's level; worker slots 1 + level/5 with UNIQUE hero assignment (a hero
staffs exactly one facility). Support boons take the BEST assignee only,
and that hero's branch picks the live mechanic (Surgeon vs Herbalist at the
Infirmary is an exclusive choice). Athenaeum: 5 disciplines x 4 tiers, one
node studied at a time, aether unseal fees, confluences unlocked by
mastering two disciplines, capstones like +3% all stats or +25% passive
gen. Skydock: one ship, one lane, crew pulled off other duties, refit
points. Reliquary: trophy pedestals 2 + level/5 vs 8 buff types (real
scarcity). Transcendence: 100k x 1.6^n gold, infusions capped by facility
level. Chronosphere: free 24h rewind button (no tradeoff). Daily gates: 3
keys x 3 gates, always run highest tier (no decision). Mirror, Tavern,
Infirmary (trauma only), Dining/Farm, Training Grounds, Bestiary.

Advertise: Athenaeum confluences; UNIQUE staffing + best-assignee branch
picks; Reliquary pedestals + level-capped Transcendence.

Thin: upgrade path identical across 21 facilities (FIX: A/B specs); Wall
removes ordering choice (FIX: permits); extra workers do nothing for boons
(FIX: minor additive); Chronosphere strictly positive; expedition lanes
answer themselves.

## 4. Economy

Exists:
- Gacha per 100k: gems 1-star 70860 / 4-star 1000 / 5-star 130 / 6-star 10;
  gold tops at 4-star 50. 7-star is UNSUMMONABLE (transcend a maxed 6-star
  with Eternal Shards, floor-80+ bosses only).
- Pity: 10-pull guarantees 3-star+. No high pity (identity, keep stated).
- Sparks: gem pulls accrue; redeem = guaranteed 5-star from a wishlist of
  up to 3 classes, editable until spent. Separate equipment spark track.
- Seasonal banner: 6-star at 0.5% (50x rate-up), hard calendar windows.
- 10-pulls can roll synergy groups; a group leader's rarity is forced above
  its followers (hidden 10-pull advantage).
- Equipment: 18 grades D- to Z (multiplier 1.8 to 100); SS/SSS/Z are
  unreachable from standard gacha, only seasonal forge / crafting / deep
  bosses. Set families need all 3 slots. Weapon TYPE affinity is a hard
  equip gate and grants a bonus Weapon Art active when matched.
- Crafting: material tier sets a hard rarity FLOOR; team Luck biases
  material tier (Luck does not scale with level, deliberately); smith
  discounts to 65%; capstone +1 rarity chance. Crafting is designed to
  overtake gear summons.
- Market: 4 static items (FIX: rotation). No currency exchange (FIX: one
  aether/materials exchange).

Advertise: Spark wishlist as the anti-whale contract; Luck -> material tier
-> rarity floor crafting chain; weapon affinity Arts.

## 5. Team building

Exists:
- Floor 41+ requires THREE full teams: `required_teams = (floor-1)//20 + 1`,
  and fatigue 10 blocks deployment (recovers over time). Roster breadth is
  enforced at the API.
- Leaders: one per team, three stacked effects scaled by star (x1 + 0.3 per
  star): squad doctrine by tendency (Stoic = fear resist 30-60%, Protective
  = def, Glory = crit), 30% targeting override, 10-28%/round panic
  steadying. Leaderless teams get nothing.
- Support classes deliver combat power FROM BASE: Priest death saves,
  Quartermaster barriers/kits, Tactician opening mana, Chef feast (up to
  +35% all stats), Spy sabotage, Tracker mark. Mastery = min(star,7) +
  evolution stage, so a grinded 3-star support matches a raw 5-star.
- Three team slots are otherwise identical buckets (FIX: formations give
  them identity).

Advertise: multi-team walls + fatigue (breadth beats whales); leader
doctrine choice per floor; base-only support classes as the anti-whale
statement.

## Cross-cutting notes
1. CLASS_EVOLUTIONS duplicate keys: FIXED 08-03.
2. Two environment systems overlap: merge planned with formations/Intel
   work (balance-affecting, not a hot-fix).
3. guild_coin does not exist in the codebase (memory said otherwise); guild
   value arrives as guild_hero_exp_pct from the arena server.
4. Skill-priority reorder was identified as a depth lever and REJECTED by
   design: the player is a manager, not a pilot. Formations carry that
   weight instead.
