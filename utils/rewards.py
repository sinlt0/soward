import random
import time
from datetime import datetime, timezone
from typing import Optional

import config
from utils import coins, db

def reward_amount(streak: int) -> int:
    return config.REWARD_BASE + min(config.REWARD_STREAK_MAX_BONUS, config.REWARD_STREAK_STEP * max(0, streak - 1))


def roll_gamble(rng: Optional[random.Random] = None) -> float:
    rng = rng or random
    point = rng.random()
    total = 0.0
    for chance, multiplier in config.GAMBLE_TIERS:
        total += chance
        if point < total:
            return multiplier
    return 0.0


def roll_diamonds(source: str, rng: Optional[random.Random] = None) -> int:
    rng = rng or random
    chance, low, high = config.DIAMOND_DROPS.get(source, (0.0, 0, 0))
    if chance <= 0 or rng.random() >= chance:
        return 0
    return rng.randint(low, high)


async def drop_diamonds(user_id: int, source: str, rng: Optional[random.Random] = None) -> int:
    amount = roll_diamonds(source, rng)
    if amount:
        await coins.add_diamonds(user_id, amount)
    return amount


async def claim_vote_diamonds(user_id: int, site: str, now: Optional[float] = None, rng: Optional[random.Random] = None) -> int:
    now = now or time.time()
    rng = rng or random
    cursor = await db.raw_execute(
        "INSERT INTO vote_diamonds (user_id, site, last_at) VALUES (?, ?, ?)"
        " ON CONFLICT(user_id, site) DO UPDATE SET last_at=excluded.last_at WHERE vote_diamonds.last_at<=?",
        (user_id, site, now, now - config.VOTE_DIAMONDS_COOLDOWN_HOURS * 3600))
    if getattr(cursor, "rowcount", 0) <= 0:
        return 0
    amount = rng.randint(config.VOTE_DIAMONDS_MIN, config.VOTE_DIAMONDS_MAX)
    await coins.add_diamonds(user_id, amount)
    return amount


def gamble_return() -> float:
    return sum(chance * multiplier for chance, multiplier in config.GAMBLE_TIERS)


async def state(user_id: int) -> dict:
    row = await db.raw_fetchone("SELECT * FROM wallet_state WHERE user_id=?", (user_id,))
    if row:
        return dict(row)
    return {"user_id": user_id, "reward_at": 0.0, "streak": 0, "work_at": 0.0, "work_day": "", "work_count": 0, "gamble_at": 0.0}


async def save(data: dict) -> None:
    await db.raw_execute(
        "INSERT INTO wallet_state (user_id, reward_at, streak, work_at, work_day, work_count, gamble_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET reward_at=excluded.reward_at, streak=excluded.streak, work_at=excluded.work_at,"
        " work_day=excluded.work_day, work_count=excluded.work_count, gamble_at=excluded.gamble_at",
        (data["user_id"], data["reward_at"], data["streak"], data["work_at"], data["work_day"], data["work_count"], data["gamble_at"]))


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def claim_reward(user_id: int, now: Optional[float] = None) -> dict:
    now = now or time.time()
    data = await state(user_id)
    wait = data["reward_at"] + config.REWARD_COOLDOWN_HOURS * 3600 - now
    if wait > 0:
        return {"ok": False, "wait": wait, "streak": data["streak"]}
    kept = now - data["reward_at"] <= config.REWARD_STREAK_WINDOW_HOURS * 3600 and data["streak"] > 0
    streak = data["streak"] + 1 if kept else 1
    amount = reward_amount(streak)
    previous = data["streak"]
    data.update(reward_at=now, streak=streak)
    await save(data)
    await coins.add(user_id, amount)
    diamonds = await drop_diamonds(user_id, "reward")
    return {"ok": True, "amount": amount, "diamonds": diamonds, "streak": streak, "reset": previous > 1 and not kept}


async def gamble_gate(user_id: int, now: Optional[float] = None) -> float:
    now = now or time.time()
    data = await state(user_id)
    wait = data["gamble_at"] + config.GAMBLE_COOLDOWN_SECONDS - now
    if wait > 0:
        return wait
    data["gamble_at"] = now
    await save(data)
    return 0.0
