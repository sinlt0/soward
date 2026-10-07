import time
import uuid
from typing import Optional

from utils import db

async def _next_case_id(guild_id: int) -> str:
    row = await db.raw_fetchone(
        "SELECT COUNT(*) as cnt FROM mod_cases WHERE guild_id=?", (guild_id,)
    )
    count = row["cnt"] if row else 0
    return f"{guild_id}-{count + 1}"

async def create_mod_case(
    guild_id: int,
    action: str,
    user_id: int,
    moderator_id: int,
    reason: Optional[str] = None,
    duration: Optional[int] = None,
) -> str:
    case_id = await _next_case_id(guild_id)
    await db.raw_execute(
        "INSERT INTO mod_cases (case_id, guild_id, action, user_id, moderator_id, reason, duration, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (case_id, guild_id, action, user_id, moderator_id, reason, duration, time.time()),
    )
    return case_id

async def create_warn(
    guild_id: int,
    user_id: int,
    moderator_id: int,
    reason: Optional[str] = None,
) -> str:
    case_id = str(uuid.uuid4())[:8].upper()
    await db.raw_execute(
        "INSERT INTO warn_cases (case_id, guild_id, user_id, moderator_id, reason, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (case_id, guild_id, user_id, moderator_id, reason, time.time()),
    )
    return case_id

async def get_warns(guild_id: int, user_id: int) -> list:
    return await db.raw_fetch(
        "SELECT * FROM warn_cases WHERE guild_id=? AND user_id=? ORDER BY created_at DESC",
        (guild_id, user_id),
    )

async def get_mod_cases(guild_id: int, user_id: Optional[int] = None) -> list:
    if user_id:
        return await db.raw_fetch(
            "SELECT * FROM mod_cases WHERE guild_id=? AND user_id=? ORDER BY created_at DESC",
            (guild_id, user_id),
        )
    return await db.raw_fetch(
        "SELECT * FROM mod_cases WHERE guild_id=? ORDER BY created_at DESC LIMIT 50",
        (guild_id,),
    )

async def delete_warn(case_id: str, guild_id: int) -> bool:
    cur = await db.raw_execute(
        "DELETE FROM warn_cases WHERE case_id=? AND guild_id=?", (case_id, guild_id)
    )
    return cur.rowcount > 0
