import datetime
import random
import time
from typing import Optional

from rpg import gear, pouch, schema, settings
from utils import coins, db

WEEKLY = (
    ("win", "Win fights", 12, 20, 1.0), ("meditate", "Meditate", 8, 14, 1.0), ("gather", "Gather herbs or ore", 12, 20, 0.9),
    ("calamity", "Defeat calamity bosses", 4, 7, 1.5), ("craft", "Forge or craft items", 4, 7, 1.2), ("explore", "Explore the wilds", 6, 10, 1.0),
    ("brew", "Brew pills", 4, 7, 1.2), ("realm", "Enter secret realms", 2, 4, 1.6), ("event", "Take part in world events", 3, 6, 1.0),
)
COUNT = 3
COINS = 160
CHEST = 640
CHEST_SLOT = 99
KINDS = {key: label for key, label, *_ in WEEKLY}


def week(now: Optional[float] = None) -> str:
    stamp = datetime.datetime.fromtimestamp(now or time.time(), datetime.timezone.utc)
    year, number, _ = stamp.isocalendar()
    return f"{year}-W{number:02d}"


def roll(period: str, user_id: int) -> list:
    rng = random.Random(f"{period}:{user_id}")
    return [(slot, kind, rng.randint(low, high)) for slot, (kind, _label, low, high, _w) in enumerate(rng.sample(WEEKLY, COUNT))]


async def generate(user_id: int, now: Optional[float] = None) -> None:
    await schema.ensure()
    period = week(now or time.time())
    for slot, kind, goal in roll(period, user_id):
        await db.raw_execute(
            "INSERT INTO cult_commissions (user_id, period, slot, kind, goal, progress, claimed) VALUES (?, ?, ?, ?, ?, 0, 0) ON CONFLICT(user_id, period, slot) DO NOTHING",
            (user_id, period, slot, kind, goal))


async def rows(user_id: int, now: Optional[float] = None) -> list:
    now = now or time.time()
    await generate(user_id, now)
    period = week(now)
    data = await db.raw_fetch("SELECT slot, kind, goal, progress, claimed FROM cult_commissions WHERE user_id=? AND period=? AND kind<>'chest' ORDER BY slot", (user_id, period))
    return [{"slot": int(r["slot"]), "kind": r["kind"], "goal": int(r["goal"]), "progress": int(r["progress"]), "claimed": int(r["claimed"]), "period": period} for r in data]


async def bump(user_id: int, key: str, amount: int = 1, now: Optional[float] = None) -> None:
    try:
        if key not in KINDS:
            return
        now = now or time.time()
        await generate(user_id, now)
        await db.raw_execute(
            "UPDATE cult_commissions SET progress=MIN(goal, progress+?) WHERE user_id=? AND period=? AND kind=? AND claimed=0",
            (amount, user_id, week(now), key))
    except Exception:
        pass


def label(row: dict) -> str:
    return f"{KINDS[row['kind']]} ({min(row['progress'], row['goal'])}/{row['goal']})"


def average(tier: int) -> float:
    return sum(settings.FIGHT_COINS[min(tier, len(settings.FIGHT_COINS) - 1)]) / 2


def worth(row: dict, tier: int) -> int:
    weight = next(w for kind, _l, _lo, _hi, w in WEEKLY if kind == row["kind"])
    return int(average(tier) * COINS / 10 * weight)


async def claim(user_id: int, tier: int, now: Optional[float] = None, rng=None) -> dict:
    rng = rng or random
    now = now or time.time()
    group = await rows(user_id, now)
    total = 0
    count = 0
    items: dict = {}
    parts: dict = {}
    for row in group:
        if row["progress"] < row["goal"] or row["claimed"]:
            continue
        cursor = await db.raw_execute("UPDATE cult_commissions SET claimed=1 WHERE user_id=? AND period=? AND slot=? AND claimed=0", (user_id, row["period"], row["slot"]))
        if getattr(cursor, "rowcount", 1) <= 0:
            continue
        total += worth(row, tier)
        count += 1
        material = gear.GRADES[min(tier, len(gear.GRADES) - 1)]["material"]
        items[material] = items.get(material, 0) + 4
        herb = gear.herb_for(rng.choice(list(gear.HERB_NAMES)), min(tier, 3))
        items[herb] = items.get(herb, 0) + 2
    bonus = 0
    if group and all(r["claimed"] or r["progress"] >= r["goal"] for r in group) and count + sum(r["claimed"] for r in group) == len(group):
        flag = await db.raw_execute(
            "INSERT INTO cult_commissions (user_id, period, slot, kind, goal, progress, claimed) VALUES (?, ?, ?, 'chest', 1, 1, 1) ON CONFLICT(user_id, period, slot) DO NOTHING",
            (user_id, group[0]["period"], CHEST_SLOT))
        if getattr(flag, "rowcount", 1) > 0:
            bonus = int(average(tier) * CHEST / 10)
            items["rift_shard"] = items.get("rift_shard", 0) + 3
            items["realm_key"] = items.get("realm_key", 0) + 2
    if count == 0 and bonus == 0:
        return {"claimed": 0}
    if total + bonus:
        await coins.add(user_id, total + bonus)
    stored = {}
    for key, qty in items.items():
        got = await pouch.stash(user_id, key, qty, parts)
        if got:
            stored[key] = got
    return {"claimed": count, "coins": total, "bonus": bonus, "items": stored, "parts": parts}
