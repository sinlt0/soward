import time
from typing import Optional

import config
from utils import db


async def balances(user_id: int) -> dict:
    row = await db.raw_fetchone("SELECT coins, diamonds FROM wallets WHERE user_id=?", (user_id,))
    if not row:
        return {"coins": 0, "diamonds": 0}
    return {"coins": int(row["coins"]), "diamonds": int(row["diamonds"])}


async def balance(user_id: int) -> int:
    return (await balances(user_id))["coins"]


async def diamonds(user_id: int) -> int:
    return (await balances(user_id))["diamonds"]


async def add(user_id: int, amount: int) -> int:
    amount = int(amount)
    if amount <= 0:
        return await balance(user_id)
    await db.raw_execute(
        "INSERT INTO wallets (user_id, coins, bought, earned, diamonds, v2, updated_at) VALUES (?, ?, 0, ?, 0, 1, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET coins=coins+excluded.coins, earned=earned+excluded.earned, updated_at=excluded.updated_at",
        (user_id, amount, amount, time.time()))
    return await balance(user_id)


async def add_diamonds(user_id: int, amount: int) -> int:
    amount = int(amount)
    if amount <= 0:
        return await diamonds(user_id)
    await db.raw_execute(
        "INSERT INTO wallets (user_id, coins, bought, earned, diamonds, v2, updated_at) VALUES (?, 0, 0, 0, ?, 1, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET diamonds=diamonds+excluded.diamonds, updated_at=excluded.updated_at",
        (user_id, amount, time.time()))
    return await diamonds(user_id)


async def spend(user_id: int, amount: int) -> bool:
    amount = int(amount)
    if amount <= 0:
        return False
    cursor = await db.raw_execute(
        "UPDATE wallets SET coins=coins-?, updated_at=? WHERE user_id=? AND coins>=?",
        (amount, time.time(), user_id, amount))
    return getattr(cursor, "rowcount", 0) > 0


async def spend_diamonds(user_id: int, amount: int) -> bool:
    amount = int(amount)
    if amount <= 0:
        return False
    cursor = await db.raw_execute(
        "UPDATE wallets SET diamonds=diamonds-?, updated_at=? WHERE user_id=? AND diamonds>=?",
        (amount, time.time(), user_id, amount))
    return getattr(cursor, "rowcount", 0) > 0


async def convert(user_id: int, amount: int) -> int:
    amount = int(amount)
    if amount <= 0:
        return 0
    gained = amount * config.DIAMOND_TO_COINS
    cursor = await db.raw_execute(
        "UPDATE wallets SET diamonds=diamonds-?, coins=coins+?, updated_at=? WHERE user_id=? AND diamonds>=?",
        (amount, gained, time.time(), user_id, amount))
    return gained if getattr(cursor, "rowcount", 0) > 0 else 0


async def transfer(sender: int, receiver: int, amount: int, currency: str = "diamonds") -> bool:
    if currency == "coins":
        if not await spend(sender, amount):
            return False
        await add(receiver, amount)
        return True
    if not await spend_diamonds(sender, amount):
        return False
    await add_diamonds(receiver, amount)
    return True


async def premium_ready_at(user_id: int) -> float:
    row = await db.raw_fetchone("SELECT bought_at FROM premium_coin_buys WHERE user_id=?", (user_id,))
    last = float(row["bought_at"]) if row else 0.0
    return last + config.PREMIUM_COIN_COOLDOWN_DAYS * 86400


async def claim_premium_slot(user_id: int) -> Optional[float]:
    now = time.time()
    row = await db.raw_fetchone("SELECT bought_at FROM premium_coin_buys WHERE user_id=?", (user_id,))
    previous = float(row["bought_at"]) if row else 0.0
    cursor = await db.raw_execute(
        "INSERT INTO premium_coin_buys (user_id, bought_at) VALUES (?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET bought_at=excluded.bought_at WHERE premium_coin_buys.bought_at<=?",
        (user_id, now, now - config.PREMIUM_COIN_COOLDOWN_DAYS * 86400))
    return previous if getattr(cursor, "rowcount", 0) > 0 else None


async def release_premium_slot(user_id: int, previous: float) -> None:
    await db.raw_execute("UPDATE premium_coin_buys SET bought_at=? WHERE user_id=?", (previous, user_id))


async def richest(limit: int = 10) -> list[dict]:
    rows = await db.raw_fetch("SELECT user_id, coins FROM wallets WHERE coins>0 ORDER BY coins DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]


def usd_to_diamonds(usd: float) -> int:
    return int(round(usd * config.DIAMOND_PER_USD))


def usd_to_coins(usd: float) -> int:
    return usd_to_diamonds(usd) * config.DIAMOND_TO_COINS


def fmt(amount: int) -> str:
    return f"{int(amount):,}"
