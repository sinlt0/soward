import time
from typing import Optional

from utils import db

TRIAL_DAYS = 3
REMIND_BEFORE_HOURS = 24


async def get(guild_id: int) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM premium_trials WHERE guild_id=?", (guild_id,))
    return dict(row) if row else None


async def start(guild_id: int, user_id: int) -> float:
    now = time.time()
    ends_at = now + TRIAL_DAYS * 86400
    await db.raw_execute(
        "INSERT INTO premium_trials (guild_id, claimed_by, claimed_at, ends_at, reminded) VALUES (?, ?, ?, ?, 0)",
        (guild_id, user_id, now, ends_at))
    await db.raw_execute(
        "INSERT INTO guilds (guild_id, premium, premium_expires_at) VALUES (?, 1, ?)"
        " ON CONFLICT(guild_id) DO UPDATE SET premium=1, premium_expires_at=excluded.premium_expires_at",
        (guild_id, ends_at))
    return ends_at


async def due_reminders() -> list[dict]:
    now = time.time()
    rows = await db.raw_fetch(
        "SELECT * FROM premium_trials WHERE reminded=0 AND ends_at>? AND ends_at<=?",
        (now, now + REMIND_BEFORE_HOURS * 3600))
    return [dict(r) for r in rows]


async def mark_reminded(guild_id: int) -> None:
    await db.raw_execute("UPDATE premium_trials SET reminded=1 WHERE guild_id=?", (guild_id,))


async def still_trial_only(guild_id: int, ends_at: float) -> bool:
    row = await db.raw_fetchone("SELECT premium, premium_expires_at FROM guilds WHERE guild_id=?", (guild_id,))
    if not row or not row["premium"] or row["premium_expires_at"] is None:
        return False
    return row["premium_expires_at"] <= ends_at + 60
