"""Build a LIBRARY of zone plates so no two players climb the same tower.

WHY. The tower has 10 zones and there were 11 plates, so every player without
generation walked through identical scenery. Zone identity is the cheapest
uniqueness in the game: a plate is shared across all players who happen to draw
it, costs nothing per player, and ten drawn from a large pool makes two towers
look unrelated.

The maths, for 10 zones drawn from L plates: the chance a given zone of yours
also appears in another player's tower is about 10/L.

    L =  11   ->  every zone shared (today)
    L =  40   ->  ~25% overlap
    L = 100   ->  ~10% overlap
    L = 200   ->   ~5% overlap

So this targets ~100+. At ~30s each that is under an hour, once, forever.

BANDS. Zones are drawn per profile from low/mid/high bands so a new player
never opens on a dragon boneyard. Each scene below declares its band, and the
filename carries it (band_slug.png) so the draw needs no lookup table.

    python tools/build_floor_library.py             # generate everything missing
    python tools/build_floor_library.py --count 40  # just the first N missing
"""

import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from PIL import Image                                            # noqa: E402
from services import comfy_service as CS                         # noqa: E402
from services.portrait_cache import ENV_GEN_NEGATIVE             # noqa: E402

OUT = os.path.join(ROOT, "frontend", "public", "images", "floor_library")
LORA = "Everspire_Floors_v1.safetensors:0.85"
GEN = (768, 1344)     # the bucket the floors LoRA trained at
SHIP = (941, 1672)    # what the zone tiles expect

# (band, slug, scene). Bands gate WHERE a zone can appear in the climb:
#   low  floors 1-30   approachable, natural, survivable
#   mid  floors 31-70  ruined, hostile, built-then-abandoned
#   high floors 71+    apocalyptic, unreal, actively wrong
SCENES = [
    # ── low ────────────────────────────────────────────────────────────────
    ("low", "root_hollows", "a root-choked underground hollow, thick tangled roots and hanging vines, glowing green fungal light"),
    ("low", "moss_stair", "a vast mossy stone stairway spiralling up a damp cavern, ferns in the cracks, shafts of pale light"),
    ("low", "flooded_undercroft", "a flooded stone undercroft, still black water to the knee, brick arches receding into dark"),
    ("low", "beast_warren", "a dug-out beast warren of packed earth tunnels, bones and matted fur, low sloping ceilings"),
    ("low", "fungal_grove", "a cavern grove of towering luminous mushrooms in drifting spore haze"),
    ("low", "quarry_pit", "an abandoned terraced quarry cut into rock, rusted machinery and spoil heaps"),
    ("low", "sunken_orchard", "a drowned orchard, dead trees standing in shallow grey water, low mist"),
    ("low", "hill_barrows", "a field of grassy burial barrows under heavy cloud, leaning standing stones"),
    ("low", "creek_gorge", "a narrow river gorge with a fast shallow creek, mossy boulders, overhanging trees"),
    ("low", "collapsed_mine", "a collapsed mine gallery with shored timbers, spilled ore carts, lantern glow"),
    ("low", "bramble_maze", "an overgrown bramble labyrinth of thorn walls twice head height"),
    ("low", "shepherds_waste", "a windswept upland waste of dry grass and broken drystone walls"),
    ("low", "salt_marsh", "a wide salt marsh at dusk, reed beds and tidal channels, wading birds gone"),
    ("low", "cinder_fields", "gently smoking cinder fields, low ash dunes, embers under a grey sky"),
    ("low", "chalk_hollow", "a white chalk hollow carved by water, pale walls, thin blue pools"),
    ("low", "hermit_terraces", "abandoned hillside terraces with collapsed hermit cells cut into the rock"),
    ("low", "willow_fen", "a still fen of drowned willows, green water, hanging curtains of leaves"),
    ("low", "boulder_field", "a chaotic boulder field beneath a cliff, house-sized rocks, thin cold light"),

    # ── mid ────────────────────────────────────────────────────────────────
    ("mid", "fallen_cathedral", "a collapsed cathedral open to the sky, vines through the vaulting, shattered rose window"),
    ("mid", "bone_aqueduct", "a ruined aqueduct striding over a dry riverbed of bones"),
    ("mid", "drowned_city", "a drowned city of tilted towers standing in black water"),
    ("mid", "siege_tunnels", "a collapsing siege tunnel with shored timbers and spilled earth, abandoned tools"),
    ("mid", "machine_hall", "a vast hall of stalled gears and hanging counterweights, chains in the dark"),
    ("mid", "ruined_library", "a ruined library of collapsed shelves and drifting loose pages"),
    ("mid", "charnel_pit", "a charnel pit ringed by iron hooks and heavy chains"),
    ("mid", "basalt_canyon", "a canyon of vertical basalt columns with a thin band of light far above"),
    ("mid", "chain_bridge", "a bridge of enormous chains spanning a chasm filled with fog"),
    ("mid", "frozen_armoury", "a frozen armoury, racked weapons furred with frost, breath-fog in still air"),
    ("mid", "mirror_hall", "a hall of tall cracked mirrors reflecting an empty room"),
    ("mid", "spider_hollow", "a hollow choked with grey webbing, wrapped shapes hanging"),
    ("mid", "sunken_temple", "a sunken temple at the bottom of a vast sinkhole, roots through the roof"),
    ("mid", "ash_bridge", "a bridge of fused bone and slag spanning a pit of drifting ash"),
    ("mid", "leviathan_ribs", "a hollow inside a colossal skeleton, ribs forming architecture overhead"),
    ("mid", "storm_rampart", "a storm-lashed fortress rampart above churning cloud, lightning between spires"),
    ("mid", "ship_graveyard", "a graveyard of beached ships, hulls rising from grey silt"),
    ("mid", "iron_foundry", "a dead foundry of cold crucibles and slag heaps, catwalks overhead"),
    ("mid", "crystal_cave", "a crystalline cave of enormous refracting shards, cold internal light"),
    ("mid", "blood_marsh", "a marsh of red water and dead reeds with sunken statues"),
    ("mid", "obsidian_stair", "an obsidian stair descending a cliff of black glass, reflections underfoot"),
    ("mid", "plague_ward", "an abandoned plague ward of rotted cots and hanging linen screens"),

    # ── high ───────────────────────────────────────────────────────────────
    ("high", "void_throne", "a throne room open to the void, its floor ending in empty space"),
    ("high", "worldtree_roots", "a cavern beneath a world-tree with roots the size of buildings"),
    ("high", "caldera_rim", "the rim of a volcanic caldera with ash falling like snow"),
    ("high", "storm_eye", "the eye of a storm, still air ringed by a wall of lightning"),
    ("high", "mirror_lake", "a black mirror lake reflecting nothing above it"),
    ("high", "shattered_orrery", "a ruined observatory open to the sky with a shattered orrery"),
    ("high", "floating_isles", "an archipelago of floating stone islands linked by hanging chains"),
    ("high", "glass_desert", "a desert of black volcanic glass under a white sun"),
    ("high", "abyssal_trench", "an abyssal trench lit by bioluminescence in black water"),
    ("high", "bleeding_spire", "an impossibly tall spire with a cliff road spiralling around it"),
    ("high", "unmade_hall", "a hall coming apart into geometry, floor tiles drifting off into dark"),
    ("high", "dragon_boneyard", "an immense dragon skeleton draped over black peaks, ribs arching above the path"),
    ("high", "ember_sea", "a sea of slow-moving molten rock with black islands and drifting embers"),
    ("high", "starless_vault", "a vault of impossible height with no ceiling, only starless dark"),
    ("high", "frozen_sea", "a frozen sea with tall ships locked upright in the ice"),
    ("high", "shrine_of_teeth", "a shrine built entirely of fused teeth and bone, lit from beneath"),
    ("high", "inverted_tower", "a tower descending into a chasm, its rooms hanging upside down"),
    ("high", "aurora_waste", "a mirrored salt flat under a violent violet aurora"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, help="only generate the first N missing")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    todo = [s for s in SCENES if not os.path.isfile(os.path.join(OUT, f"{s[0]}_{s[1]}.png"))]
    if args.count:
        todo = todo[:args.count]

    bands = {}
    for b, _, _ in SCENES:
        bands[b] = bands.get(b, 0) + 1
    print(f"library: {len(SCENES)} scenes ({bands}) — {len(todo)} still to generate")
    if args.dry_run:
        return 0

    if not CS.is_comfy_running():
        CS.ensure_comfy_running()
        for _ in range(120):
            if CS.is_comfy_running():
                break
            time.sleep(4)
    if not CS.is_comfy_running():
        print("ComfyUI never came up — aborting.")
        return 1

    made = failed = 0
    t0 = time.time()
    for i, (band, slug, scene) in enumerate(todo, 1):
        dest = os.path.join(OUT, f"{band}_{slug}.png")
        prompt = (f"no humans, no creatures, empty scenery, dark fantasy, {scene}, "
                  f"intricate detailed background, atmospheric lighting, "
                  f"masterpiece, best quality, very awa, absurdres")
        wf = CS._build_workflow(prompt, negative=ENV_GEN_NEGATIVE, seed=770000 + i * 613,
                                width=GEN[0], height=GEN[1], hires=True,
                                lora_override=LORA, face_detail=False,
                                transparent=False, rembg_cutout=False)
        pid = CS._queue_prompt(wf)
        fn = CS._wait_for_result(pid) if pid else None
        if fn and CS._download_image(fn, dest):
            # Backgrounds stay opaque — never cut these out.
            Image.open(dest).convert("RGB").resize(SHIP, Image.LANCZOS).save(dest)
            made += 1
        else:
            failed += 1
            print(f"  FAILED {band}_{slug}", flush=True)
        if i % 5 == 0 or i == len(todo):
            rate = (time.time() - t0) / max(made, 1)
            print(f"  [{i}/{len(todo)}] {made} made, {failed} failed, "
                  f"~{(len(todo)-i)*rate/60:.0f}m left", flush=True)

    print(f"\n{made} made, {failed} failed -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
