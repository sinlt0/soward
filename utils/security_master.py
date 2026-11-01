import time
from typing import Optional

from utils import db, guild_settings

KEY = "security_master_off"
SCOPE_KEYS = {"verification": "security_pause_verification"}
DEFAULT_SECONDS = 2 * 3600
MAX_SECONDS = 7 * 86400


def _key(scope: Optional[str]) -> str:
    return SCOPE_KEYS[scope] if scope else KEY


async def state(guild_id: int, scope: Optional[str] = None) -> Optional[dict]:
    value = await guild_settings.get(guild_id, _key(scope), None)
    return value if isinstance(value, dict) else None


def _active(current: Optional[dict]) -> bool:
    if not current:
        return False
    until = current.get("until")
    return until is None or time.time() < float(until)


async def is_off(guild_id: int, scope: Optional[str] = None) -> bool:
    if _active(await state(guild_id)):
        return True
    return bool(scope) and _active(await state(guild_id, scope))


async def expired(guild_id: int, scope: Optional[str] = None) -> Optional[dict]:
    current = await state(guild_id, scope)
    if current and current.get("until") is not None and time.time() >= float(current["until"]):
        return current
    return None


async def disable(guild_id: int, actor_id: Optional[int], reason: str, seconds: int, scope: Optional[str] = None) -> dict:
    seconds = max(300, min(MAX_SECONDS, int(seconds)))
    current = {"at": time.time(), "by": actor_id, "reason": reason[:200], "until": time.time() + seconds}
    await guild_settings.set(guild_id, _key(scope), current)
    return current


async def enable(guild_id: int, scope: Optional[str] = None) -> Optional[dict]:
    current = await state(guild_id, scope)
    await guild_settings.delete(guild_id, _key(scope))
    if scope in (None, "verification"):
        await db.raw_execute("UPDATE pending_verification SET joined_at=? WHERE guild_id=?", (time.time(), guild_id))
    return current
