import time
import uuid
from typing import Optional

from utils import db


async def create(guild_id: int, name: str, role_id: int, period_start: float, period_end: float, claim_until: float, created_by: int) -> str:
    badge_id = uuid.uuid4().hex[:6].upper()
    await db.raw_execute(
        "INSERT INTO commemorative_badges (badge_id, guild_id, name, role_id, period_start, period_end, claim_until, closed, created_by, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
        (badge_id, guild_id, name[:60], role_id, period_start, period_end, claim_until, created_by, time.time()))
    return badge_id


async def get(guild_id: int, badge_id: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM commemorative_badges WHERE guild_id=? AND badge_id=?", (guild_id, badge_id.upper()))
    return dict(row) if row else None


async def listing(guild_id: int) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM commemorative_badges WHERE guild_id=? ORDER BY period_start DESC", (guild_id,))
    return [dict(r) for r in rows]


async def open_overdue(now: float) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM commemorative_badges WHERE closed=0 AND claim_until<=?", (now,))
    return [dict(r) for r in rows]


async def update(badge_id: str, **fields) -> None:
    names = ", ".join(f"{k}=?" for k in fields)
    await db.raw_execute(f"UPDATE commemorative_badges SET {names} WHERE badge_id=?", (*fields.values(), badge_id))


async def delete(badge_id: str) -> None:
    await db.raw_execute("DELETE FROM commemorative_badges WHERE badge_id=?", (badge_id,))
    await db.raw_execute("DELETE FROM badge_claims WHERE badge_id=?", (badge_id,))


async def claimed(badge_id: str, user_id: int) -> bool:
    return await db.raw_fetchone("SELECT 1 FROM badge_claims WHERE badge_id=? AND user_id=?", (badge_id, user_id)) is not None


async def record(badge_id: str, user_id: int) -> None:
    await db.raw_execute(
        "INSERT INTO badge_claims (badge_id, user_id, claimed_at) VALUES (?, ?, ?) ON CONFLICT(badge_id, user_id) DO NOTHING", (badge_id, user_id, time.time()))


async def claim_count(badge_id: str) -> int:
    row = await db.raw_fetchone("SELECT COUNT(*) AS c FROM badge_claims WHERE badge_id=?", (badge_id,))
    return int(row["c"]) if row else 0


async def drop_role(guild_id: int, role_id: int) -> None:
    for badge in await listing(guild_id):
        if badge["role_id"] == role_id:
            await delete(badge["badge_id"])


def eligible(joined_at: Optional[float], badge: dict) -> bool:
    return joined_at is not None and joined_at <= badge["period_end"]


def claim_state(badge: dict, now: float) -> str:
    if badge["closed"] or now >= badge["claim_until"]:
        return "closed"
    return "open"
