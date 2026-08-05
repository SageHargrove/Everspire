# tools/

Split into ACTIVE and `oneoff/` on 2026-08-05, because after many sessions it
had become impossible to tell which scripts still matter. Nothing was deleted —
`oneoff/` is superseded or single-use work, kept because several encode
findings that are cheaper to re-read than to rediscover.

## Art generation — current

| script | what it does |
|---|---|
| `gen_missing_enemies.py` | Generates every enemy portrait the game lacks, into `enemies/<tier>/`. Use this, NOT `oneoff/regen_monsters.py`, which stages flat and lands art in the wrong folder. |
| `build_base_pool.py` | Builds the shipped hero pool (class x gender x star ladder). `COMFY_LORA_HERO` overrides the adapter. |
| `build_zone_library.py` | Invents and renders tower zones. Names, blurbs and art all come from `llm_service.generate_zone`, the same function a GPU player calls. |
| `reband_zones.py` | Moves a zone between low/mid/high, keeping filename and manifest in step. |

## Review and QA

| script | what it does |
|---|---|
| `enemy_sheet.py` | Contact sheets of the roster grouped BY BODY PLAN, so a systematic failure shows as a whole group looking wrong. |
| `zone_contact_sheet.py` | Contact sheets per band. |
| `check_zone_plates.py` | Flags plates too dark to sit behind hero cutouts. Thresholds calibrated against real output. |
| `ab_monster_lora.py` | A/Bs two monster LoRAs on identical prompts AND seeds. The only honest way to judge a retrain — seed variance moves quality more than most adapter changes do. |
| `recut_hero_cutouts.py` | Re-cuts hero art with the current algorithm, keeping `.prev.bak` so a bad pass rolls back. |

## Training and long jobs

| script | what it does |
|---|---|
| `train_monsters_v2.sh` | Single monster LoRA train. |
| `overnight_retrain.sh` | Unattended chain: build datasets, train both LoRAs, ship them, regenerate enemies. |
| `overnight_heroes.sh` | Stage 2 — waits for hero training, then rebuilds the pool. Separate FILE on purpose: bash reads a script by byte offset as it runs, so editing a live one makes it resume at the wrong place. |
| `keep_awake.ps1` | Suppresses sleep while a long job runs, releases itself after. ASCII-only and decimal constants — see its header for why both matter on PS 5.1. |
| `stop_generation.ps1` | Kills ComfyUI and generation scripts. Use this: `pkill` and `ps -W \| grep` both fail silently here. |

## Build and release

`make_release.py`, `make_icon.py`, `giltgrave.iss`

## oneoff/

Superseded or single-use. Read before reusing:

- `regen_monsters.py` — stages art FLAT, and its `--adopt` lands everything in
  `enemies/` root instead of `enemies/<tier>/`. The game then keeps reading the
  old art and the run looks like it worked. Superseded by `gen_missing_enemies.py`.
- `build_floor_library.py` — hand-written zone list. Superseded by
  `build_zone_library.py`, which generates zones from the same function players use.
- `regen_zone_floors.py` — one-time migration off the manhwa adapters.
- `make_icon_v2.py`, `make_icon_painted.py`, `make_icon_variants.py` — icon
  explorations; `make_icon.py` is the one that shipped.
- `v2_scale_test.py` — broad sample of one monster LoRA across body plans.
  Useful pattern if you ever need it again: six samples cannot show a body plan
  that collapses, twenty can.
- `gen_equipment_sample.py` — 8-icon comparison for the equipment art decision.
- `run_art_queue.sh` — superseded by the overnight chain scripts.
