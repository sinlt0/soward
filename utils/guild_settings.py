import json
from typing import Any, Optional

from utils import db

_cache: dict[tuple, Any] = {}

async def get(guild_id: int, key: str, default: Any = None) -> Any:
    cache_key = (guild_id, key)
    if cache_key in _cache:
        return _cache[cache_key]

    row = await db.raw_fetchone(
        "SELECT setting_value FROM guild_settings WHERE guild_id=? AND setting_key=?",
        (guild_id, key),
    )
    if row is None:
        return default

    try:
        value = json.loads(row["setting_value"])
    except (json.JSONDecodeError, TypeError):
        value = row["setting_value"]

    _cache[cache_key] = value
    return value

async def set(guild_id: int, key: str, value: Any) -> None:
    _cache[(guild_id, key)] = value
    serialized = json.dumps(value)
    await db.raw_execute(
        "INSERT INTO guild_settings (guild_id, setting_key, setting_value) VALUES (?, ?, ?)"
        " ON CONFLICT(guild_id, setting_key) DO UPDATE SET setting_value=excluded.setting_value",
        (guild_id, key, serialized),
    )

async def delete(guild_id: int, key: str) -> None:
    _cache.pop((guild_id, key), None)
    await db.raw_execute(
        "DELETE FROM guild_settings WHERE guild_id=? AND setting_key=?",
        (guild_id, key),
    )

async def get_all(guild_id: int) -> dict:
    rows = await db.raw_fetch(
        "SELECT setting_key, setting_value FROM guild_settings WHERE guild_id=?",
        (guild_id,),
    )
    result = {}
    for row in rows:
        try:
            result[row["setting_key"]] = json.loads(row["setting_value"])
        except (json.JSONDecodeError, TypeError):
            result[row["setting_key"]] = row["setting_value"]
    return result
