# Character cutouts — how it works, and what not to "fix"

Portraits generate on a black void and have to end up as transparent PNGs.
This has been rewritten several times, each time re-learning the same lesson,
so this file is the record.

## The one rule

**Segmentation decides the figure. Colour/connectivity may only ADD to it.**

Any cutout that decides "dark region touching the frame = background" will
destroy this art. Black cloaks, black hair and black trousers sit against a
black void with an antialiased outline between them, and wherever that outline
dips below threshold — one pixel is enough — a flood fill walks through the gap
and eats the garment from inside. Measured on the shipped hero pool 2026-08-02:
severed braids, hollowed thighs, capes reduced to tatters.

No threshold fixes it. At a black-on-black boundary there is no difference to
find. It needs a model that knows what a person looks like.

The union runs one direction on purpose: a pixel wrongly kept is black on a
black void and invisible; a pixel wrongly dropped punches a hole through a
character. **When in doubt, keep it.**

## Where the code lives

    generation/comfy_nodes/toe_rembg/cutout.py     ← THE algorithm. One copy.
    generation/comfy_nodes/toe_rembg/__init__.py   ← thin ComfyUI node wrapper
    backend/services/portrait_cache.py             ← imports cutout.py by path

`cutout.py` imports nothing from the game, so it runs inside ComfyUI's python
too. It previously existed twice — a weaker copy in the node, a stronger one in
the backend — and they drifted: node-cut portraits had no hole reclaim and no
trim, so the same art came out different depending on which path ran it. Don't
re-fork it.

## Which path actually runs

**Normal case — inside ComfyUI.** `COMFY_REMBG_CUTOUT` defaults to `1`, the
`ToE_RembgCutout` node runs last in the workflow, and the portrait arrives
already transparent. `portrait_cache._has_real_alpha` sees real alpha and the
backend does nothing.

**Node missing** (install failed, ComfyUI not restarted, `COMFY_REMBG_CUTOUT=0`)
— the workflow queue 400s, `comfy_service` retries without the node, and the
portrait comes back on its black void. `_cutout_with_heal` then walks:

| rung | needs | competence |
|---|---|---|
| `_rembg_union_cutout` → `cutout.py` | rembg, numpy, scipy | best; the real thing |
| `make_game_cutout` | numpy, scipy | non-humanoids, lit backdrops |
| `_border_flood_cutout` | PIL only | last resort; **hollows dark costumes** |

The frozen build deliberately excludes `rembg`/`onnxruntime` (~200MB for a path
most players never reach), so on a player's machine rung 1 is normally
unavailable and the node is doing the work. That is the whole reason the
algorithm lives next to the node rather than in the backend.

## Monsters are different — do not "unify" this

`isnet-anime` segments anime **characters**. On a spider, a corvid, a dragon or
a heavily armoured revenant it returns ~0% and `cutout_rgba` returns `None`.

Re-cutting all 123 enemy portraits with it produced **1 improvement and 110
regressions** (`death_knight` −44% of kept area, `mordane` −28%). Enemy art was
never cut by the broken flood — it goes through `make_game_cutout` and is
already correct. `tools/recut_hero_cutouts.py` therefore excludes monsters by
default and auto-reverts any re-cut that loses >1.5pp of kept area.

## Repairing existing art

    python tools/recut_hero_cutouts.py            # heroes, from retained masters
    python tools/recut_hero_cutouts.py --dry-run

No GPU. Keeps a one-time `.prev.bak` per file, measures against that original
rather than the previous run, auto-reverts regressions, and writes a
before/after contact sheet to `docs/cutout-repair.png`. Run 2026-08-02:
147 heroes repaired, best +24.4% of frame recovered, 0 regressions.

Heroes in a profile's `alive/` dir have no retained master and need
regeneration instead.

## Things already tried that do not work

- **Border flood as primary** (07-19 → 08-02). The failure this whole file is
  about. It was adopted despite the same investigation concluding it "SHREDS
  dark clothing", because it was wired as the first rung and therefore always
  won.
- **A stricter/looser flood threshold.** There is no separating value.
- **Eroding the alpha** to hide the flood's dark fringe. Eats thin features
  (braids, blades, cape edges) and widens every existing hole.
- **`_cutout_ok` as the gate for the union.** Its "bright ⇒ figure" premise
  only holds on a void master; on a lit backdrop it rejected 36 perfectly good
  segmentations. The union carries its own gate.
- **LayerDiffuse native-transparent generation.** Dead end with the vPred
  NoobAI checkpoint — see the notes in `portrait_cache.py`.
