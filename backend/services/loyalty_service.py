"""Affinity as EARNED trust, not just bought attention.

Affinity (0-100, on heroes) already existed, but every source moved it one
way and none of them were the Tower: gifts, the Sanctum, base activities and
training all ADD, and nothing anywhere subtracts. A manager could get their
whole roster killed floor after floor and, so long as they handed out enough
presents, every survivor still adored them. The track measured attention, not
trust — which is why the schema comment called it "consumed by upcoming
loyalty mechanics" and nothing consumed it.

This is the consumer. Outcomes in the Tower now move affinity too:

  * you brought them home            -> up a little
  * you brought them home BARELY     -> up more (you got them out)
  * someone died                     -> down for the whole roster, because
                                        everyone hears about it
  * the floor wiped                  -> down hard

Gifts still work, and still matter. They just stop being sufficient on their
own: you cannot buy your way out of being a manager who loses people.

Deliberately roster-wide on the loss side. Judging an individual deployment
was tried and abandoned — a Blacksmith kept at base, a training run on an
early floor, and a team picked for chemistry over raw power all look like
"you sent the weak ones" to any per-deployment metric, and none of them are.
The aggregate record has no such edge cases: heroes don't resent one order,
they form a view of the person giving them.
"""

# Survivors. Small numbers on purpose — this accrues over a climb rather than
# swinging on any single floor.
TRUST_SURVIVED = 1
TRUST_SURVIVED_BARELY = 2      # walked off at death's door and lived
BARELY_HP_FRACTION = 0.15

# Losses, applied to EVERY living hero, not just the squad that was there.
TRUST_PER_DEATH = -3
TRUST_WIPE_BONUS = -5          # on top of the per-death cost
MAX_DEATH_PENALTY = -15        # a catastrophe is a catastrophe; don't zero the roster


def survivor_trust_delta(current_hp: int, max_hp: int) -> int:
    """What one hero makes of having been brought back alive."""
    if max_hp > 0 and current_hp <= max_hp * BARELY_HP_FRACTION:
        return TRUST_SURVIVED_BARELY
    return TRUST_SURVIVED


def roster_trust_delta(death_count: int, wiped: bool) -> int:
    """What the whole roster makes of the losses, capped so a single disaster
    can't flatten every relationship in the base to zero."""
    if death_count <= 0:
        return 0
    delta = death_count * TRUST_PER_DEATH
    if wiped:
        delta += TRUST_WIPE_BONUS
    return max(MAX_DEATH_PENALTY, delta)


def apply_floor_trust(conn, surviving: list[dict], dead_ids: list, wiped: bool) -> dict:
    """Commit both halves of a floor's trust movement.

    Order matters: the roster-wide loss lands first so a survivor of a fatal
    floor nets out roughly flat rather than being rewarded for a disaster
    they walked out of.
    """
    roster_delta = roster_trust_delta(len(dead_ids or []), wiped)
    if roster_delta:
        conn.execute(
            "UPDATE heroes SET affinity = MAX(0, MIN(100, COALESCE(affinity, 0) + ?)) "
            "WHERE is_alive = 1",
            (roster_delta,),
        )

    per_hero = {}
    for s in surviving or []:
        hid = s.get("id")
        if hid is None or hid in set(dead_ids or []):
            continue
        row = conn.execute("SELECT max_health FROM heroes WHERE id = ?", (hid,)).fetchone()
        if not row:
            continue
        delta = survivor_trust_delta(s.get("health", 0), row["max_health"] or 0)
        conn.execute(
            "UPDATE heroes SET affinity = MAX(0, MIN(100, COALESCE(affinity, 0) + ?)) WHERE id = ?",
            (delta, hid),
        )
        per_hero[hid] = delta

    return {"roster_delta": roster_delta, "survivor_deltas": per_hero}
