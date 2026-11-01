import time
from typing import Optional

from utils import db


async def record(user_id: int, usd: float) -> dict:
    now = time.time()
    await db.raw_execute(
        "INSERT INTO supporters (user_id, total_usd, tips, public, display_name, first_at, last_at) VALUES (?, ?, 1, 0, '', ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET total_usd=total_usd+excluded.total_usd, tips=tips+1, last_at=excluded.last_at",
        (user_id, round(usd, 2), now, now))
    return await get(user_id)


async def get(user_id: int) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM supporters WHERE user_id=?", (user_id,))
    return dict(row) if row else None


async def set_public(user_id: int, public: bool, display_name: str) -> bool:
    row = await get(user_id)
    if row is None:
        return False
    await db.raw_execute("UPDATE supporters SET public=?, display_name=? WHERE user_id=?", (1 if public else 0, display_name[:40] if public else "", user_id))
    return True


async def public_list(limit: int = 100) -> list[dict]:
    rows = await db.raw_fetch("SELECT user_id, display_name, total_usd, last_at FROM supporters WHERE public=1 AND display_name<>'' ORDER BY total_usd DESC, last_at DESC LIMIT ?", (limit,))
    return [{"name": r["display_name"], "total": round(r["total_usd"], 2), "last_at": r["last_at"]} for r in rows]


async def is_supporter(user_id: int) -> bool:
    return await get(user_id) is not None
