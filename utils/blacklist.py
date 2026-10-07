from time import time

from utils import db

_user_cache: set[int] = set()
_guild_cache: set[int] = set()
_loaded = False


async def _ensure_loaded():
    global _loaded
    if _loaded:
        return
    rows = await db.raw_fetch("SELECT target_id, target_type FROM blacklist")
    for row in rows:
        if row["target_type"] == "user":
            _user_cache.add(row["target_id"])
        else:
            _guild_cache.add(row["target_id"])
    _loaded = True


async def is_user_blacklisted(user_id: int) -> bool:
    await _ensure_loaded()
    return user_id in _user_cache


async def is_guild_blacklisted(guild_id: int) -> bool:
    await _ensure_loaded()
    return guild_id in _guild_cache


async def add(target_id: int, target_type: str, reason: str, blacklisted_by: int) -> None:
    await _ensure_loaded()
    await db.raw_execute(
        "INSERT OR REPLACE INTO blacklist (target_id, target_type, reason, blacklisted_by, created_at) VALUES (?, ?, ?, ?, ?)",
        (target_id, target_type, reason, blacklisted_by, time()),
    )
    if target_type == "user":
        _user_cache.add(target_id)
    else:
        _guild_cache.add(target_id)


async def remove(target_id: int, target_type: str) -> bool:
    await _ensure_loaded()
    cur = await db.raw_execute(
        "DELETE FROM blacklist WHERE target_id=? AND target_type=?", (target_id, target_type)
    )
    if target_type == "user":
        _user_cache.discard(target_id)
    else:
        _guild_cache.discard(target_id)
    return cur.rowcount > 0
