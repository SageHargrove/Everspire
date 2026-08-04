# Giltgrave — Art & Icon Drop Manifest

Everything below is **already wired in code**. Each asset renders the moment
you drop the correctly-named file into its folder. Until then a graceful
fallback shows (letter monogram, hand-built glyph, woven placeholder, or the
plain text label) — nothing ever breaks or shows a broken-image square.

---

## 1. Recolorable line-icon SVGs — `public/icons/<set>/<NAME>.svg`

Rendered by `components/Sigil.jsx` as a **CSS mask** so each icon takes its
context color (`currentColor`). Author them as single-color `currentColor`
SVGs, 24×24 viewBox, stroke ~1.4. UPPER_SNAKE filenames (except `ui/`).

| set | wired in | naming | files |
|-----|----------|--------|-------|
| `status/` | Combat status chips (CombatArena) | UPPER_SNAKE | ✅ present (11) |
| `facility/` | Base facility cards + detail header + Lobby card (BasePage) | UPPER_SNAKE of facility type; backend "Wall" aliases to `THE_WALL.svg`; Vault / Transcendence Core have no icon (letter fallback) | ✅ present (18) |
| `floor/` | Floor badges + type callout (TowerPage) | see floor list below | ✅ present (9) |
| `class-base/` | Hero ClassBadge everywhere | UPPER_SNAKE of **base family**; "Magic Engineer" → `M_ENGINEER.svg`; no CLASSLESS (PNG fallback) | ✅ present (18) |
| `class-evolution/` | (reserved for per-tier badges) | `BASE_EVOLUTION.svg` e.g. `THIEF_ROGUE.svg` | ✅ present (131) |
| `ui/` | Top-bar nav cluster + currency pills + back button | **lowercase**, e.g. `friends.svg`, `currency-gold.svg` | ✅ present (15) |

**`floor/` names (9):** `STANDARD_COMBAT` `MINIBOSS` `BOSS_ROOM` `ELITE_COMBAT`
`SURVIVAL_SWARM` `NARRATIVE_EVENT` `ESCORT` `RETRIEVAL` `BLITZ`
(multiple gameplay types intentionally share one — all miniboss variants →
`MINIBOSS`; defend/conquest/war/ambush → `ELITE_COMBAT`; event/explore/cursed → `NARRATIVE_EVENT`.)

**`class-base/` names (19):** `WARRIOR` `SPEARMAN` `THIEF` `ARCHER` `MAGE`
`SPELLSWORD` `ACOLYTE` `PRIEST` `TACTICIAN` `SCOUT` `BLACKSMITH` `CHEF` `MEDIC`
`QUARTERMASTER` `FARMER` `MERCHANT` `ALCHEMIST` `MAGIC_ENGINEER` `CLASSLESS`
(every evolution tier inherits its base family's sigil — see `CLASS_FAMILIES` in HeroCard.jsx.)

**`ui/` names wired now:** `friends` `mail` `chat` `guild-crest` `menu`
(each falls back to the hand-built mockup glyph if absent).

---

## 2. Full-color background/art PNGs — `public/images/<kind>/<slug>.png`

Rendered as `<img>`/CSS backgrounds, **lowercase_snake** slugs.

| kind | path | naming | wired in | status |
|------|------|--------|----------|--------|
| Floor biomes | `images/floors/<slug>.png` | zone slug (`overgrown_caverns` …) | TowerPage zone grid bg | ✅ 10 present |
| Battleships | `images/battleships/ship_<tier>.png` | `ship_1`…`ship_5` | BasePage Skydock | ✅ 5 present |
| Facility art | `images/facilities/<slug>.png` | lowercase facility type, e.g. `mage_tower.png` ("Wall" → `the_wall.png`) | BasePage facility card art panel | ⬜ drop in |

To **replace** existing floor/ship art, just overwrite the same filename.

---

## Legacy sets still in service (do not delete)
- `icons/*.png` (~134 loose) — the flat `GameIcon` set (`/icons/<name>.png`):
  item/material/equipment/star-tier icons still used across Inventory, Summon,
  Market, etc. Class-family PNGs among them are now only the ClassBadge
  *fallback*.
- `icons/banners/` + `icons/emblems/` — Banner Studio & TeamBanner art
  (PNG masks + emblems). No replacement designs exist yet; when new banner
  art lands, overwrite `banner_tier1-4.png` / the emblem PNGs in place.

## Notes
- `Sigil` probes each file once (module-level cache) and shows the fallback
  until it confirms the file loads — safe to have wired before files exist.
- If a facility/floor slug ever produces the wrong filename, the rule is
  literally `type.toLowerCase().replace(/ /g,'_')` (art) or `.toUpperCase()`
  (sigil) — no per-name table to maintain.
