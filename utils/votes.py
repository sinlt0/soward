import time
from typing import Optional

import config
from utils import db


async def get(user_id: int) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM votes WHERE user_id=?", (user_id,))
    return dict(row) if row else None


async def record(user_id: int, source: str) -> dict:
    now = time.time()
    row = await get(user_id)
    window = config.VOTE_STREAK_WINDOW_HOURS * 3600
    streak = (row["streak"] + 1) if row and now - row["last_vote_at"] <= window else 1
    total = (row["total"] if row else 0) + 1
    until = now + config.VOTE_NP_HOURS * 3600
    await db.raw_execute(
        "INSERT INTO votes (user_id, total, streak, last_vote_at, np_until, last_source) VALUES (?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET total=excluded.total, streak=excluded.streak, last_vote_at=excluded.last_vote_at,"
        " np_until=excluded.np_until, last_source=excluded.last_source",
        (user_id, total, streak, now, until, source))
    return await get(user_id)


async def active_np() -> dict[int, float]:
    rows = await db.raw_fetch("SELECT user_id, np_until FROM votes WHERE np_until>?", (time.time(),))
    return {r["user_id"]: r["np_until"] for r in rows}
