from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict
import json
import random

from database import db
from services.equipment_service import save_equipment, origin_forged
from services.llm_service import generate_creative_craft

router = APIRouter()

class PremadeCraftReq(BaseModel):
    crafter_id: int
    recipe_id: int
    # Forge minigame result — the STRIKE THE STEEL timing game's quality
    # multiplier. 1.0 = auto-resolve baseline (skipping is never punished,
    # it's a clean NOVICE run); higher tiers push toward ×3 on LEGENDARY.
    # 0 is the CATASTROPHE sentinel: a botched Legendary attempt — the gold
    # and materials are consumed and NOTHING is made. Server-clamped so a
    # modified client can't mint god-gear.
    quality_mult: float = 1.0

class CreativeCraftReq(BaseModel):
    crafter_id: int
    description: str
    materials: Dict[str, int] # e.g. {"Iron": 5, "Demon Core": 1}

@router.get("/recipes")
def get_recipes():
    with db() as conn:
        recipes = conn.execute("SELECT * FROM recipes WHERE is_discovered = 1").fetchall()
        return [dict(r) for r in recipes]

@router.post("/craft/premade")
def craft_premade(req: PremadeCraftReq):
    with db() as conn:
        recipe = conn.execute("SELECT * FROM recipes WHERE id = ?", (req.recipe_id,)).fetchone()
        if not recipe: raise HTTPException(status_code=404, detail="Recipe not found")
        
        crafter = conn.execute("SELECT name, level, apt_tactical FROM heroes WHERE id = ? AND is_alive = 1", (req.crafter_id,)).fetchone()
        if not crafter: raise HTTPException(status_code=400, detail="Crafter not found or dead")
        
        base_row = conn.execute("SELECT gold, materials FROM base WHERE id = 1").fetchone()
        gold = base_row["gold"]
        inv_mats = json.loads(base_row["materials"]) if base_row["materials"] else {}
        
        req_mats = json.loads(recipe["materials_json"])

        # Support revamp: a Blacksmith assigned to the Forge discounts crafting
        # gold costs by star (support_service.CRAFT_DISCOUNT, up to 45% at 7★).
        # Cheaper, never free — materials are always paid in full.
        gold_cost = recipe["gold_cost"]
        smith_rarity_chance = 0.0
        try:
            from services.support_service import get_support_effects
            _sfx = get_support_effects(conn)
            disc = _sfx.get("craft_discount_pct", 0)
            smith_rarity_chance = _sfx.get("smith_rarity_chance", 0)
            if disc:
                gold_cost = max(1, int(gold_cost * (1 - disc / 100.0)))
        except Exception:
            pass

        if gold < gold_cost:
            raise HTTPException(status_code=400, detail=f"Not enough gold. Need {gold_cost}")

        from services.materials_service import get_material_total, consume_material
        for m, qty in req_mats.items():
            if get_material_total(inv_mats, m) < qty:
                raise HTTPException(status_code=400, detail=f"Not enough {m}. Need {qty}.")

        # Deduct
        new_gold = gold - gold_cost
        for m, qty in req_mats.items():
            consume_material(inv_mats, m, qty)

        conn.execute("UPDATE base SET gold = ?, materials = ? WHERE id = 1", (new_gold, json.dumps(inv_mats)))
        
        # Forge minigame CATASTROPHE (quality 0, Legendary botch): the gold
        # and materials above are already spent — the piece is slag. No item.
        if (req.quality_mult or 1.0) <= 0.05:
            return {"success": False, "ruined": True, "quality": 0,
                    "message": "The final strike lands wrong — the steel shears, and the work is ruined."}

        # Craft it! The power of the equipment is based on the crafter's level/aptitude AND the recipe's base_stat_mult
        power_pool = (crafter["level"] * 5) + int(crafter["apt_tactical"] * 0.5)
        power_pool = int(power_pool * recipe["base_stat_mult"])
        # Forge minigame quality — clamped hard server-side (see PremadeCraftReq).
        quality = max(0.3, min(3.0, req.quality_mult or 1.0))
        power_pool = int(power_pool * quality)
        
        # Allocate power randomly but weighted
        stats = {"base_str": 0, "base_int": 0, "base_hlt": 0, "base_end": 0, "base_wil": 0, "base_luck": 0, "base_agi": 0}
        
        if recipe["type"] == "weapon":
            primary = "base_str"
            stats[primary] += int(power_pool * 0.6)
            rem = power_pool - stats[primary]
            stats["base_agi"] += int(rem * 0.5)
            stats["base_luck"] += rem - int(rem * 0.5)
        elif recipe["type"] == "armor":
            primary = "base_end"
            stats[primary] += int(power_pool * 0.6)
            rem = power_pool - stats[primary]
            stats["base_hlt"] += int(rem * 0.8)
            stats["base_wil"] += rem - int(rem * 0.8)
        else: # accessory
            stats["base_int"] += int(power_pool * 0.3)
            stats["base_wil"] += int(power_pool * 0.3)
            stats["base_luck"] += int(power_pool * 0.4)
            
        # Master Smith capstone: a chance the piece comes out a cut above —
        # +1 rarity and 30% hotter stats (allocated pool bumped in place).
        import random as _rand
        crafted_rarity = "B" if (smith_rarity_chance and _rand.random() < smith_rarity_chance) else "C"
        if crafted_rarity == "B":
            for k in stats:
                stats[k] = int(stats[k] * 1.3)
        equip = {
            "name": f"Crafted {recipe['name']}",
            "type": recipe["type"],
            "rarity": crafted_rarity,
            "level": crafter["level"],
            **stats,
            "str_pct": 0.0, "int_pct": 0.0, "hlt_pct": 0.0, "agi_pct": 0.0, "def_pct": 0.0, "end_pct": 0.0, "wil_pct": 0.0, "luck_pct": 0.0, "regen_pct": 0.0
        }
        
        # Stamp the maker. Only forged gear carries this — it's what lets a
        # legendary piece credit the smith later, from wherever it ends up.
        equip["crafted_by"] = req.crafter_id
        equip["origin"] = origin_forged(crafter["name"] if crafter else None)
        equip_id = save_equipment(equip, conn)
        equip["id"] = equip_id

        from services.deeds_service import record_craft_deed
        record_craft_deed(conn, req.crafter_id, equip["name"], equip.get("rarity"))

    from services.quests_service import bump as bump_rite
    bump_rite("craft")
    return {"success": True, "equipment": equip, "quality": quality, "masterwork": crafted_rarity == "B"}

@router.post("/craft/creative")
def craft_creative(req: CreativeCraftReq):
    with db() as conn:
        crafter = conn.execute("SELECT name, level, apt_tactical FROM heroes WHERE id = ? AND is_alive = 1", (req.crafter_id,)).fetchone()
        if not crafter: raise HTTPException(status_code=400, detail="Crafter not found")
        
        base_row = conn.execute("SELECT materials FROM base WHERE id = 1").fetchone()
        inv_mats = json.loads(base_row["materials"]) if base_row["materials"] else {}
        
        for m, qty in req.materials.items():
            if inv_mats.get(m, 0) < qty:
                raise HTTPException(status_code=400, detail=f"Not enough {m}. Need {qty}.")
                
        # Deduct
        for m, qty in req.materials.items():
            inv_mats[m] -= qty
        conn.execute("UPDATE base SET materials = ? WHERE id = 1", (json.dumps(inv_mats),))
        
        # Calculate raw power pool based on crafter
        power_pool = (crafter["level"] * 5) + int(crafter["apt_tactical"] * 0.5)
        
        # Call LLM to generate the equipment and the recipe
        equip, recipe_name, recipe_desc = generate_creative_craft(req.description, req.materials, power_pool, crafter["level"])
        
        # Save Equipment
        equip["crafted_by"] = req.crafter_id
        equip["origin"] = origin_forged(crafter["name"] if crafter else None)
        equip_id = save_equipment(equip, conn)
        equip["id"] = equip_id

        from services.deeds_service import record_craft_deed
        record_craft_deed(conn, req.crafter_id, equip.get("name", "a nameless work"), equip.get("rarity"))
        
        # Save Recipe
        conn.execute(
            "INSERT INTO recipes (name, type, description, materials_json, gold_cost, base_stat_mult, is_discovered) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (recipe_name, equip["type"], recipe_desc, json.dumps(req.materials), 250, 1.2)
        )

    from services.quests_service import bump as bump_rite
    bump_rite("craft")
    return {"success": True, "equipment": equip, "new_recipe": recipe_name}
