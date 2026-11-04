import time
from typing import Optional

import config
from utils import coins, db


def pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


async def slots(user_id: int) -> dict:
    row = await db.raw_fetchone("SELECT marriage_slots, adopt_slots FROM family_slots WHERE user_id=?", (user_id,))
    if row:
        return {"marriage": int(row["marriage_slots"]), "adopt": int(row["adopt_slots"])}
    return {"marriage": config.MARRIAGE_SLOTS_DEFAULT, "adopt": config.ADOPT_SLOTS_DEFAULT}


async def partners(user_id: int) -> list[int]:
    rows = await db.raw_fetch("SELECT user_a, user_b, married_at FROM marriages WHERE user_a=? OR user_b=? ORDER BY married_at", (user_id, user_id))
    return [r["user_b"] if r["user_a"] == user_id else r["user_a"] for r in rows]


async def marriage(a: int, b: int) -> Optional[dict]:
    x, y = pair(a, b)
    row = await db.raw_fetchone("SELECT * FROM marriages WHERE user_a=? AND user_b=?", (x, y))
    return dict(row) if row else None


async def parent_of(child_id: int) -> Optional[int]:
    row = await db.raw_fetchone("SELECT parent_id FROM family_children WHERE child_id=?", (child_id,))
    return int(row["parent_id"]) if row else None


async def children_of(user_id: int) -> list[int]:
    rows = await db.raw_fetch("SELECT child_id FROM family_children WHERE parent_id=? ORDER BY adopted_at", (user_id,))
    return [int(r["child_id"]) for r in rows]


async def is_ancestor(candidate: int, user_id: int) -> bool:
    current = user_id
    for _ in range(50):
        current = await parent_of(current)
        if current is None:
            return False
        if current == candidate:
            return True
    return True


async def marry_blocker(a: int, b: int) -> Optional[str]:
    if await marriage(a, b):
        return "You are already married to each other."
    if await parent_of(a) == b or await parent_of(b) == a:
        return "A parent and child cannot marry."
    for user in (a, b):
        limit = (await slots(user))["marriage"]
        if len(await partners(user)) >= limit:
            return "marriage_full:%d" % user
    return None


async def marry(a: int, b: int) -> None:
    x, y = pair(a, b)
    await db.raw_execute("INSERT OR IGNORE INTO marriages (user_a, user_b, married_at) VALUES (?, ?, ?)", (x, y, time.time()))


async def divorce(a: int, b: int) -> bool:
    x, y = pair(a, b)
    cursor = await db.raw_execute("DELETE FROM marriages WHERE user_a=? AND user_b=?", (x, y))
    return getattr(cursor, "rowcount", 0) > 0


async def adopt_blocker(parent: int, child: int) -> Optional[str]:
    if await parent_of(child) is not None:
        return "That person already has a parent."
    if await marriage(parent, child):
        return "You cannot adopt your partner."
    if await is_ancestor(child, parent):
        return "You cannot adopt someone in your own line of parents."
    limit = (await slots(parent))["adopt"]
    if len(await children_of(parent)) >= limit:
        return "adopt_full"
    return None


async def adopt(parent: int, child: int) -> None:
    await db.raw_execute("INSERT OR IGNORE INTO family_children (child_id, parent_id, adopted_at) VALUES (?, ?, ?)", (child, parent, time.time()))


async def release(child: int) -> bool:
    cursor = await db.raw_execute("DELETE FROM family_children WHERE child_id=?", (child,))
    return getattr(cursor, "rowcount", 0) > 0


async def upgrade(user_id: int, kind: str) -> tuple[bool, str]:
    current = await slots(user_id)
    if kind == "marriage":
        cost, maximum, key = config.MARRIAGE_SLOT_COST, config.MARRIAGE_SLOTS_MAX, "marriage"
    else:
        cost, maximum, key = config.ADOPT_SLOT_COST, config.ADOPT_SLOTS_MAX, "adopt"
    if current[key] >= maximum:
        return False, "maxed"
    if not await coins.spend(user_id, cost):
        return False, "coins"
    current[key] += 1
    await db.raw_execute(
        "INSERT INTO family_slots (user_id, marriage_slots, adopt_slots) VALUES (?, ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET marriage_slots=excluded.marriage_slots, adopt_slots=excluded.adopt_slots",
        (user_id, current["marriage"], current["adopt"]))
    return True, str(current[key])


async def component(user_id: int, limit: int = 80) -> dict:
    seen = {user_id}
    frontier = [user_id]
    couples: dict[tuple[int, int], float] = {}
    parents: dict[int, tuple[int, float]] = {}
    truncated = False
    while frontier:
        marks = ",".join("?" * len(frontier))
        values = tuple(frontier)
        married = await db.raw_fetch(f"SELECT user_a, user_b, married_at FROM marriages WHERE user_a IN ({marks}) OR user_b IN ({marks})", values + values)
        kids = await db.raw_fetch(f"SELECT child_id, parent_id, adopted_at FROM family_children WHERE child_id IN ({marks}) OR parent_id IN ({marks})", values + values)
        found = []
        for row in married:
            a, b = int(row["user_a"]), int(row["user_b"])
            couples[(a, b)] = float(row["married_at"])
            found.extend((a, b))
        for row in kids:
            child, parent = int(row["child_id"]), int(row["parent_id"])
            parents[child] = (parent, float(row["adopted_at"]))
            found.extend((child, parent))
        frontier = []
        for member in found:
            if member in seen:
                continue
            if len(seen) >= limit:
                truncated = True
                continue
            seen.add(member)
            frontier.append(member)
    return {
        "nodes": seen,
        "couples": {pair_: ts for pair_, ts in couples.items() if pair_[0] in seen and pair_[1] in seen},
        "parents": {c: v for c, v in parents.items() if c in seen and v[0] in seen},
        "truncated": truncated,
    }
