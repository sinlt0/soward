import random
import time
from typing import Optional

from rpg import gear, quest, schema, settings
from utils import coins, db


async def tiers(user_id: int) -> dict:
    await schema.ensure()
    rows = await db.raw_fetch("SELECT kind, tier FROM cult_pouches WHERE user_id=?", (user_id,))
    result = {kind: 0 for kind in gear.POUCHES}
    for row in rows:
        if row["kind"] in result:
            result[row["kind"]] = int(row["tier"])
    return result


async def usage(user_id: int) -> dict:
    held = await tiers(user_id)
    rows = await db.raw_fetch("SELECT item, qty FROM cult_items WHERE user_id=? AND qty>0", (user_id,))
    used = {kind: 0 for kind in gear.POUCHES}
    for row in rows:
        kind = gear.pool(row["item"])
        if kind:
            used[kind] += int(row["qty"])
    return {kind: {"used": used[kind], "cap": gear.pouch_cap(held[kind]), "tier": held[kind]} for kind in gear.POUCHES}


async def put(user_id: int, key: str, qty: int) -> None:
    await db.raw_execute(
        "INSERT INTO cult_items (user_id, item, qty) VALUES (?, ?, ?) ON CONFLICT(user_id, item) DO UPDATE SET qty=qty+excluded.qty",
        (user_id, key, qty))


async def stash(user_id: int, key: str, qty: int, parts: Optional[dict] = None) -> int:
    kind = gear.pool(key)
    if qty <= 0:
        return 0
    if not kind:
        await put(user_id, key, qty)
        return qty
    info = (await usage(user_id))[kind]
    room = max(0, info["cap"] - info["used"])
    stored = min(qty, room)
    if stored:
        await put(user_id, key, stored)
    extra = qty - stored
    if extra:
        amount = extra * gear.value(key)
        await coins.add(user_id, amount)
        if parts is not None:
            parts["overflow"] = parts.get("overflow", 0) + amount
            parts["overflow_items"] = parts.get("overflow_items", 0) + extra
    return stored


async def upgrade(user_id: int, kind: str) -> dict:
    from rpg import engine
    if kind not in gear.POUCHES:
        return {"ok": False, "reason": "unknown"}
    character = await engine.get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    held = (await tiers(user_id))[kind]
    if held >= len(gear.POUCH_TIERS):
        return {"ok": False, "reason": "max"}
    step = gear.POUCH_TIERS[held]
    material = gear.POUCHES[kind]["material"]
    cursor = await db.raw_execute("UPDATE cult_items SET qty=qty-? WHERE user_id=? AND item=? AND qty>=?", (step["materials"], user_id, material, step["materials"]))
    if getattr(cursor, "rowcount", 0) <= 0:
        return {"ok": False, "reason": "materials", "need": step["materials"], "material": material}
    if step["shards"]:
        cursor = await db.raw_execute("UPDATE cult_items SET qty=qty-? WHERE user_id=? AND item=? AND qty>=?", (step["shards"], user_id, "rift_shard", step["shards"]))
        if getattr(cursor, "rowcount", 0) <= 0:
            await put(user_id, material, step["materials"])
            return {"ok": False, "reason": "materials", "need": step["shards"], "material": "rift_shard"}
    if not await coins.spend(user_id, step["coins"]):
        await put(user_id, material, step["materials"])
        if step["shards"]:
            await put(user_id, "rift_shard", step["shards"])
        return {"ok": False, "reason": "coins", "cost": step["coins"]}
    await db.raw_execute(
        "INSERT INTO cult_pouches (user_id, kind, tier) VALUES (?, ?, ?) ON CONFLICT(user_id, kind) DO UPDATE SET tier=excluded.tier",
        (user_id, kind, held + 1))
    return {"ok": True, "kind": kind, "tier": held + 1, "step": step}


async def sell(user_id: int, key: str, qty: int) -> dict:
    if not gear.pool(key) or qty <= 0:
        return {"ok": False, "reason": "unknown"}
    cursor = await db.raw_execute("UPDATE cult_items SET qty=qty-? WHERE user_id=? AND item=? AND qty>=?", (qty, user_id, key, qty))
    if getattr(cursor, "rowcount", 0) <= 0:
        return {"ok": False, "reason": "missing"}
    amount = qty * gear.value(key)
    await coins.add(user_id, amount)
    return {"ok": True, "coins": amount, "qty": qty}


def find(text: str) -> Optional[str]:
    flat = text.strip().lower().replace("-", " ").replace(" ", "_")
    for key, info in gear.MATERIALS.items():
        if flat in (key, info["name"].lower().replace(" ", "_")):
            return key
    matches = [key for key, info in gear.MATERIALS.items() if flat in key or flat in info["name"].lower().replace(" ", "_")]
    return matches[0] if len(matches) == 1 else None


def roll_herbs(realm: int, rng: random.Random) -> dict:
    tier = min(realm, 3)
    found: dict = {}
    pool = [key for key, info in gear.HERBS.items() if info["tier"] == tier]
    for key in rng.sample(pool, min(settings.GATHER_HERB_KINDS, len(pool))):
        found[key] = rng.randint(*settings.GATHER_HERB_QTY)
    if tier < 3 and rng.randint(1, 100) <= settings.GATHER_UP_CHANCE:
        key = rng.choice([k for k, info in gear.HERBS.items() if info["tier"] == tier + 1])
        found[key] = found.get(key, 0) + 1
    if rng.randint(1, 100) <= settings.GATHER_FIBER_CHANCE:
        found["spirit_fiber"] = rng.randint(1, 2)
    return found


def roll_hunt(realm: int, rng: random.Random) -> dict:
    found = {gear.GRADES[min(realm, 3)]["material"]: rng.randint(*settings.HUNT_QTY)}
    if rng.randint(1, 100) <= settings.GATHER_HIDE_CHANCE:
        found["beast_hide"] = rng.randint(1, 2)
    return found


async def gather(user_id: int, mode: str, rng: Optional[random.Random] = None, now: Optional[float] = None) -> dict:
    from rpg import engine
    rng = rng or random.Random()
    now = now or time.time()
    character = await engine.get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    if mode not in ("herbs", "hunt"):
        return {"ok": False, "reason": "unknown"}
    if character["injured_until"] > now:
        return {"ok": False, "reason": "hurt", "wait": character["injured_until"] - now}
    left = await engine.claim_daily(user_id, "cult_gather", settings.GATHER_DAILY, now)
    if left is None:
        return {"ok": False, "reason": "limit"}
    found = roll_herbs(character["realm"], rng) if mode == "herbs" else roll_hunt(character["realm"], rng)
    parts: dict = {}
    stored = {}
    for key, qty in found.items():
        stored[key] = await stash(user_id, key, qty, parts)
    await quest.bump(user_id, "gather")
    return {"ok": True, "mode": mode, "found": found, "stored": stored, "overflow": parts.get("overflow", 0), "left": left}
