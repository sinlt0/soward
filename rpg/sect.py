import random
import secrets
import time
from typing import Optional

from rpg import bestiary, combat, engine, gear, settings
from utils import clans, coins, db

OFFICER = clans.ROLE_ORDER["officer"]


def level_cap(clan: dict) -> int:
    return min(settings.BUILDING_MAX, clan["level"])


def cost_of(level: int) -> int:
    return settings.BUILDING_COSTS[min(level, len(settings.BUILDING_COSTS) - 1)]


async def build(clan_id: str, building: str) -> dict:
    clan = await clans.get(clan_id)
    if clan is None or building not in settings.BUILDINGS:
        return {"ok": False, "reason": "unknown"}
    engine.SECT_CACHE.pop(clan_id, None)
    levels = await engine.building_levels(clan_id)
    current = levels.get(building, 0)
    if current >= settings.BUILDING_MAX:
        return {"ok": False, "reason": "max"}
    if current >= level_cap(clan):
        return {"ok": False, "reason": "tier", "cap": level_cap(clan)}
    cost = cost_of(current)
    cursor = await db.raw_execute("UPDATE clans SET bank=bank-? WHERE clan_id=? AND bank>=?", (cost, clan_id, cost))
    if getattr(cursor, "rowcount", 0) <= 0:
        return {"ok": False, "reason": "bank", "cost": cost}
    await db.raw_execute("INSERT OR IGNORE INTO clan_buildings (clan_id, building, level) VALUES (?, ?, 0)", (clan_id, building))
    cursor = await db.raw_execute("UPDATE clan_buildings SET level=level+1 WHERE clan_id=? AND building=? AND level=?", (clan_id, building, current))
    engine.SECT_CACHE.pop(clan_id, None)
    if getattr(cursor, "rowcount", 0) <= 0:
        await db.raw_execute("UPDATE clans SET bank=bank+? WHERE clan_id=?", (cost, clan_id))
        return {"ok": False, "reason": "race"}
    return {"ok": True, "level": current + 1, "cost": cost}


async def boss_row(clan_id: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM clan_boss WHERE clan_id=?", (clan_id,))
    return dict(row) if row else None


async def boss_current(clan_id: str, now: Optional[float] = None) -> Optional[dict]:
    now = now or time.time()
    clan = await clans.get(clan_id)
    if clan is None:
        return None
    row = await boss_row(clan_id)
    stale = row is None or (not row["killed"] and now - row["spawned_at"] > settings.BOSS_DAYS * 86400) or (row["killed"] and now - row["killed_at"] > settings.BOSS_RESPAWN_HOURS * 3600)
    if not stale:
        return row
    options = [boss for boss in bestiary.CLAN_BOSSES if boss["level"] <= clan["level"]]
    boss = random.choice(options)
    hp = settings.BOSS_HP_PER_MEMBER * max(5, await clans.member_count(clan_id))
    await db.raw_execute(
        "INSERT INTO clan_boss (clan_id, boss, hp, max_hp, spawned_at, killed, killed_at) VALUES (?, ?, ?, ?, ?, 0, 0)"
        " ON CONFLICT(clan_id) DO UPDATE SET boss=excluded.boss, hp=excluded.hp, max_hp=excluded.max_hp, spawned_at=excluded.spawned_at, killed=0, killed_at=0",
        (clan_id, boss["key"], hp, hp, now))
    await db.raw_execute("DELETE FROM clan_boss_hits WHERE clan_id=?", (clan_id,))
    return await boss_row(clan_id)


def boss_info(key: str) -> dict:
    return next(boss for boss in bestiary.CLAN_BOSSES if boss["key"] == key)


async def boss_hits(clan_id: str, limit: int = 5) -> list[dict]:
    rows = await db.raw_fetch("SELECT user_id, damage FROM clan_boss_hits WHERE clan_id=? ORDER BY damage DESC LIMIT ?", (clan_id, limit))
    return [dict(row) for row in rows]


async def boss_start(user_id: int, now: Optional[float] = None) -> dict:
    now = now or time.time()
    mine = await clans.membership(user_id)
    if mine is None:
        return {"ok": False, "reason": "no_clan"}
    character = await engine.get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    if engine.hurt(character, now):
        return {"ok": False, "reason": "hurt", "wait": engine.hurt(character, now)}
    row = await boss_current(mine["clan_id"], now)
    if row["killed"] or row["hp"] <= 0:
        return {"ok": False, "reason": "dead", "row": row}
    left = await engine.claim_daily(user_id, "cult_clanboss", settings.BOSS_DAILY, now)
    if left is None:
        return {"ok": False, "reason": "limit"}
    info = boss_info(row["boss"])
    state = combat.new_fight(character, engine.fight_mods(character), "grey_wolf")
    base = bestiary.BOSSES[bestiary.boss_for(character["realm"])]
    size = combat.scale(character["realm"], character["stage"])
    hp = int(100 * size * base["hp"] * settings.BOSS_PERSONAL_HP)
    state["m"].update({"key": info["key"], "name": info["name"], "zh": info["zh"], "skill": info["skill"], "hp": hp, "max": hp,
                       "atk": 14 * size * base["atk"], "def": 4 * size * base["def"]})
    state["clan_boss"] = mine["clan_id"]
    state["limit"] = settings.BOSS_TURNS
    return {"ok": True, "state": state, "left": left}


async def boss_finish(user_id: int, state: dict, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    rng = rng or random
    clan_id = state["clan_boss"]
    m = state["m"]
    character = await engine.get(user_id)
    fraction = max(0.0, min(1.0, (m["max"] - max(0, m["hp"])) / m["max"]))
    units = int(1000 * fraction * (1 + (character["realm"] if character else 0)))
    parts: dict = {"damage": units}
    if state["done"] == "lose" and character is not None:
        engine.settle(character, now)
        loss = min(character["qi"], int(engine.need(character) * settings.FIGHT_DEFEAT_QI))
        character["qi"] -= loss
        parts["qi_lost"] = loss
        await engine.save(character)
    if units <= 0:
        return {"result": state["done"], "parts": parts}
    cursor = await db.raw_execute("UPDATE clan_boss SET hp=MAX(hp-?, 0) WHERE clan_id=? AND killed=0 AND hp>0", (units, clan_id))
    if getattr(cursor, "rowcount", 0) <= 0:
        parts["damage"] = 0
        return {"result": state["done"], "parts": parts, "late": True}
    await db.raw_execute(
        "INSERT INTO clan_boss_hits (clan_id, user_id, damage) VALUES (?, ?, ?)"
        " ON CONFLICT(clan_id, user_id) DO UPDATE SET damage=damage+excluded.damage",
        (clan_id, user_id, units))
    cursor = await db.raw_execute("UPDATE clan_boss SET killed=1, killed_at=? WHERE clan_id=? AND hp<=0 AND killed=0", (now, clan_id))
    outcome = {"result": state["done"], "parts": parts}
    if getattr(cursor, "rowcount", 0) > 0:
        outcome["killed"] = True
        outcome["payouts"] = await boss_payout(clan_id, rng)
    return outcome


async def boss_payout(clan_id: str, rng) -> dict:
    clan = await clans.get(clan_id)
    hits = await boss_hits(clan_id, 1000)
    if not hits:
        return {}
    average = sum(hit["damage"] for hit in hits) / len(hits)
    payouts: dict = {}
    for hit in hits:
        character = await engine.get(hit["user_id"])
        if character is None:
            continue
        tier = min(character["realm"], len(settings.FIGHT_COINS) - 1)
        low, high = settings.FIGHT_COINS[tier]
        ratio = hit["damage"] / average if average else 1
        amount = int((low + high) / 2 * settings.BOSS_COINS_MULT * (0.5 + min(1.5, ratio)))
        await coins.add(hit["user_id"], amount)
        entry: dict = {"coins": amount, "damage": hit["damage"]}
        material = gear.GRADES[tier]["material"]
        count = rng.randint(2, 4)
        await engine.add_item(hit["user_id"], material, count)
        entry["material"] = (material, count)
        if rng.randint(1, 100) <= settings.BOSS_GEAR_CHANCE:
            drop = gear.drop(rng, tier)
            await engine.add_item(hit["user_id"], drop)
            entry["gear"] = drop
        payouts[hit["user_id"]] = entry
    if clan is not None:
        await db.raw_execute("UPDATE clans SET bank=bank+? WHERE clan_id=?", (settings.BOSS_BANK_PER_LEVEL * clan["level"], clan_id))
    return payouts


async def settle_wars(now: Optional[float] = None) -> None:
    now = now or time.time()
    await db.raw_execute("DELETE FROM clan_wars WHERE status='pending' AND created_at<?", (now - settings.WAR_PENDING_HOURS * 3600,))
    rows = await db.raw_fetch("SELECT * FROM clan_wars WHERE status='active' AND ends_at<=?", (now,))
    for row in rows:
        war = dict(row)
        a, b = war["score_a"], war["score_b"]
        winner = war["clan_a"] if a > b else war["clan_b"] if b > a else ""
        top = max(a, b)
        result = "draw"
        cursor = await db.raw_execute("UPDATE clan_wars SET status='done' WHERE war_id=? AND status='active'", (war["war_id"],))
        if getattr(cursor, "rowcount", 0) <= 0:
            continue
        if winner and top >= settings.WAR_MIN_SCORE:
            loser = war["clan_b"] if winner == war["clan_a"] else war["clan_a"]
            loser_clan = await clans.get(loser)
            stake = min(int(loser_clan["bank"] * settings.WAR_STAKE_PCT), settings.WAR_STAKE_MAX) if loser_clan else 0
            if stake > 0:
                cursor = await db.raw_execute("UPDATE clans SET bank=bank-? WHERE clan_id=? AND bank>=?", (stake, loser, stake))
                if getattr(cursor, "rowcount", 0) > 0:
                    await db.raw_execute("UPDATE clans SET bank=bank+? WHERE clan_id=?", (stake, winner))
            result = f"won:{winner}:{stake}"
        await db.raw_execute("UPDATE clan_wars SET result=? WHERE war_id=?", (result, war["war_id"]))


async def war_of(clan_id: str, now: Optional[float] = None) -> Optional[dict]:
    now = now or time.time()
    await settle_wars(now)
    row = await db.raw_fetchone(
        "SELECT * FROM clan_wars WHERE (clan_a=? OR clan_b=?) AND status IN ('pending', 'active') ORDER BY created_at DESC", (clan_id, clan_id))
    return dict(row) if row else None


async def last_war(clan_id: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM clan_wars WHERE (clan_a=? OR clan_b=?) AND status='done' ORDER BY ends_at DESC", (clan_id, clan_id))
    return dict(row) if row else None


async def officer_clan(user_id: int) -> Optional[dict]:
    mine = await clans.membership(user_id)
    if mine is None or clans.ROLE_ORDER[mine["role"]] < OFFICER:
        return None
    return await clans.get(mine["clan_id"])


async def declare(user_id: int, target_name: str, now: Optional[float] = None) -> dict:
    now = now or time.time()
    clan = await officer_clan(user_id)
    if clan is None:
        return {"ok": False, "reason": "rank"}
    target = await clans.find(target_name)
    if target is None:
        return {"ok": False, "reason": "unknown"}
    if target["clan_id"] == clan["clan_id"]:
        return {"ok": False, "reason": "self"}
    if clan["level"] < settings.WAR_MIN_TIER or target["level"] < settings.WAR_MIN_TIER:
        return {"ok": False, "reason": "tier"}
    if await war_of(clan["clan_id"], now) or await war_of(target["clan_id"], now):
        return {"ok": False, "reason": "busy"}
    for side in (clan, target):
        last = await last_war(side["clan_id"])
        if last and now - last["ends_at"] < settings.WAR_COOLDOWN_HOURS * 3600:
            return {"ok": False, "reason": "cooldown", "clan": side, "wait": settings.WAR_COOLDOWN_HOURS * 3600 - (now - last["ends_at"])}
    war_id = secrets.token_hex(4)
    await db.raw_execute(
        "INSERT INTO clan_wars (war_id, clan_a, clan_b, status, score_a, score_b, declared_by, created_at, ends_at, result) VALUES (?, ?, ?, 'pending', 0, 0, ?, ?, 0, '')",
        (war_id, clan["clan_id"], target["clan_id"], user_id, now))
    return {"ok": True, "clan": clan, "target": target}


async def respond(user_id: int, accept: bool, now: Optional[float] = None) -> dict:
    now = now or time.time()
    clan = await officer_clan(user_id)
    if clan is None:
        return {"ok": False, "reason": "rank"}
    war = await war_of(clan["clan_id"], now)
    if war is None or war["status"] != "pending" or war["clan_b"] != clan["clan_id"]:
        return {"ok": False, "reason": "none"}
    if accept:
        await db.raw_execute("UPDATE clan_wars SET status='active', ends_at=?, created_at=? WHERE war_id=? AND status='pending'", (now + settings.WAR_HOURS * 3600, now, war["war_id"]))
    else:
        await db.raw_execute("DELETE FROM clan_wars WHERE war_id=? AND status='pending'", (war["war_id"],))
    return {"ok": True, "accepted": accept, "war": war}
