# `item` sigil set

House line-sigils for inventory items — materials, mob drops and consumables.
Same style as `status/`, `equip/`, `class-base/`: 24×24, `fill:none`,
`stroke:currentColor`, `stroke-width:1.4`, round caps and joins. Rendered via
`<Sigil set="item" name="ORE" />`, which masks the SVG so it takes the
element's `color`.

**Not one icon per item.** Three axes:

| axis | carries | cost |
|---|---|---|
| **GLYPH** | what kind of thing it is | one SVG, reused forever |
| **COLOUR** | tier / quality (existing D→Z palette) | free — CSS mask recolour |
| **VARIANT** | ordered sub-tier, only where needed (potions) | one SVG per step |

So `Iron Ore` and `Mithril` are the **same glyph in two colours**, and the
drop table can grow to hundreds of entries without new art. Potions escalate
by **vessel ornateness, never by fill** — every tier is drawn full.

## Material / drop glyphs → the 33 names in `materials_service.py`

| glyph | covers |
|---|---|
| `CRYSTAL` | Dark Crystal, Runed Crystal, Void Crystal, Celestial Shard |
| `ORE` | Iron Ore, Copper *(raw, unrefined)* |
| `INGOT` | Steel, Refined Iron, Enchanted Steel, Mithril, Adamantine *(refined)* |
| `BONE` | Monster Bone, Hardened Bone, Dracolich Marrow |
| `FANG` | Dragon Fang, Vampire Fang |
| `HORN` | Imp Horn, Pit Fiend Horn |
| `TALON` | Griffon Talon |
| `SCALE` | Wyvern Scale, Dragon Scale |
| `HIDE` | Leather, Wolf Pelt, Ogre Hide, Lizard Hide |
| `CLOTH` | Tattered Cloth |
| `FEATHER` | Harpy Feather, Phoenix Feather |
| `DUST` | Mystic Dust, Spirit Dust |
| `ICHOR` | Demon Ichor |
| `SINEW` | Troll Sinew |
| `TROPHY` | Goblin Ear *(and future bounty tokens)* |

15 glyphs, 33 names, and the tier letter supplies the colour.

## Consumable glyphs

| glyph | covers |
|---|---|
| `POTION_LESSER` | Minor Healing Draught, Mana Draught, lesser tonics |
| `POTION_MEDIUM` | Healing/Mana Draught (mid), Strength Tonic, Calming Tonic |
| `POTION_GREATER` | Greater Healing/Mana Draught, Vitality Elixir, Panacea |
| `MEAL` | Baked Potato, Mandrake Stew, Honeyed Rations, Hero's Feast |
| `BANDAGE` | Bandage, Bandage Bundle |
| `CHARM` | Lucky Clover Charm, Heart Locket, War Horse Figurine |
| `CRATE` | Raw Material Crate, Ingredient Cart/Basket, Supplies |
| `WHETSTONE` | Mastercraft Whetstone |
| `SCROLL` | scrolls |

**Colour convention for potions:** green = health, blue = mana. The same three
vessels serve any future line (stamina, antidote) by colour alone.

Summon-ticket art stays as-is — it survives icon scale because it's a flat
silhouette, and it's a "money object" the player stops to look at.

## Not yet wired

These files exist but nothing renders them yet. Wiring means pointing
`ItemIcon` / the vault grid at `<Sigil set="item" …>` via a name→glyph lookup
built from the tables above. Deliberately left for sign-off.
