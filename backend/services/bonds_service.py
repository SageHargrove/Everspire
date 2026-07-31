from database import db

def get_bond(conn, hero_a_id: int, hero_b_id: int) -> int:
    a, b = min(hero_a_id, hero_b_id), max(hero_a_id, hero_b_id)
    row = conn.execute("SELECT bond_level FROM hero_bonds WHERE hero_a_id = ? AND hero_b_id = ?", (a, b)).fetchone()
    return row["bond_level"] if row else 0

def get_pairwise_bonds(hero_ids: list[int]) -> dict:
    """{(lower_id, higher_id): bond_level} for every bonded pair in the list.

    get_team_bonds_multiplier() collapses this to a per-hero total, which is
    all a stat bonus needs. Combat needs the pairs themselves: when a hero
    falls, who specifically was close to *them* decides who reacts.
    """
    if not hero_ids or len(hero_ids) < 2:
        return {}
    placeholders = ",".join("?" for _ in hero_ids)
    query = f"""
        SELECT hero_a_id, hero_b_id, bond_level
        FROM hero_bonds
        WHERE hero_a_id IN ({placeholders}) AND hero_b_id IN ({placeholders})
    """
    with db() as conn:
        rows = conn.execute(query, tuple(hero_ids) * 2).fetchall()
    return {(r["hero_a_id"], r["hero_b_id"]): r["bond_level"] for r in rows}


def get_team_bonds_multiplier(hero_ids: list[int]) -> dict:
    """
    Returns a dictionary of {hero_id: total_bond_level} for the active team.
    Each hero gets a 1% stat boost per total bond level they share with teammates in this combat.
    """
    if not hero_ids or len(hero_ids) < 2:
        return {h: 0 for h in hero_ids}
        
    placeholders = ",".join("?" for _ in hero_ids)
    query = f"""
        SELECT hero_a_id, hero_b_id, bond_level 
        FROM hero_bonds 
        WHERE hero_a_id IN ({placeholders}) AND hero_b_id IN ({placeholders})
    """
    params = tuple(hero_ids) * 2
    
    bond_totals = {h: 0 for h in hero_ids}
    with db() as conn:
        rows = conn.execute(query, params).fetchall()
        for r in rows:
            a, b, lvl = r["hero_a_id"], r["hero_b_id"], r["bond_level"]
            bond_totals[a] += lvl
            bond_totals[b] += lvl
            
    return bond_totals
