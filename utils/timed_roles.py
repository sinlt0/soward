import time
import uuid
from datetime import datetime
from typing import Optional

from utils import db


async def grant(guild_id: int, user_id: int, role_id: int, expires_at: float, granted_by: Optional[int], reason: str = "", season_id: Optional[str] = None) -> None:
    await db.raw_execute(
        "INSERT INTO timed_roles (guild_id, user_id, role_id, expires_at, granted_by, reason, season_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(guild_id, user_id, role_id) DO UPDATE SET expires_at=excluded.expires_at, granted_by=excluded.granted_by, reason=excluded.reason, season_id=excluded.season_id",
        (guild_id, user_id, role_id, expires_at, granted_by, reason[:200], season_id, time.time()))


async def get(guild_id: int, user_id: int, role_id: int) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM timed_roles WHERE guild_id=? AND user_id=? AND role_id=?", (guild_id, user_id, role_id))
    return dict(row) if row else None


async def remove(guild_id: int, user_id: int, role_id: int) -> None:
    await db.raw_execute("DELETE FROM timed_roles WHERE guild_id=? AND user_id=? AND role_id=?", (guild_id, user_id, role_id))


async def for_member(guild_id: int, user_id: int) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM timed_roles WHERE guild_id=? AND user_id=? ORDER BY expires_at", (guild_id, user_id))
    return [dict(r) for r in rows]


async def listing(guild_id: int, limit: int = 25) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM timed_roles WHERE guild_id=? ORDER BY expires_at LIMIT ?", (guild_id, limit))
    return [dict(r) for r in rows]


async def due(now: float) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM timed_roles WHERE expires_at<=?", (now,))
    return [dict(r) for r in rows]


async def drop_role(guild_id: int, role_id: int) -> None:
    await db.raw_execute("DELETE FROM timed_roles WHERE guild_id=? AND role_id=?", (guild_id, role_id))


async def create_season(guild_id: int, name: str, role_id: int, starts_at: float, ends_at: float, created_by: int, yearly: bool) -> str:
    season_id = uuid.uuid4().hex[:6].upper()
    await db.raw_execute(
        "INSERT INTO seasonal_roles (season_id, guild_id, name, role_id, starts_at, ends_at, yearly, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (season_id, guild_id, name[:60], role_id, starts_at, ends_at, 1 if yearly else 0, created_by, time.time()))
    return season_id


async def get_season(guild_id: int, season_id: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM seasonal_roles WHERE guild_id=? AND season_id=?", (guild_id, season_id.upper()))
    return dict(row) if row else None


async def seasons(guild_id: Optional[int] = None) -> list[dict]:
    if guild_id is None:
        rows = await db.raw_fetch("SELECT * FROM seasonal_roles ORDER BY starts_at")
    else:
        rows = await db.raw_fetch("SELECT * FROM seasonal_roles WHERE guild_id=? ORDER BY starts_at", (guild_id,))
    return [dict(r) for r in rows]


async def update_season(season_id: str, **fields) -> None:
    names = ", ".join(f"{k}=?" for k in fields)
    await db.raw_execute(f"UPDATE seasonal_roles SET {names} WHERE season_id=?", (*fields.values(), season_id))


async def delete_season(season_id: str) -> None:
    await db.raw_execute("DELETE FROM seasonal_roles WHERE season_id=?", (season_id,))


def next_year(ts: float) -> float:
    dt = datetime.fromtimestamp(ts)
    try:
        return dt.replace(year=dt.year + 1).timestamp()
    except ValueError:
        return dt.replace(year=dt.year + 1, day=28).timestamp()


def window_state(season: dict, now: float) -> str:
    if now < season["starts_at"]:
        return "upcoming"
    if now >= season["ends_at"]:
        return "ended"
    return "open"


def season_window(start_md: tuple[int, int], end_md: tuple[int, int], tz, now: float) -> tuple[float, float]:
    year = datetime.fromtimestamp(now, tz).year
    wraps = tuple(end_md) <= tuple(start_md)
    for offset in (-1, 0, 1):
        start = datetime(year + offset, start_md[0], start_md[1], tzinfo=tz)
        end = datetime(year + offset + (1 if wraps else 0), end_md[0], end_md[1], tzinfo=tz)
        if end.timestamp() > now:
            return start.timestamp(), end.timestamp()
    start = datetime(year + 2, start_md[0], start_md[1], tzinfo=tz)
    return start.timestamp(), datetime(year + 2 + (1 if wraps else 0), end_md[0], end_md[1], tzinfo=tz).timestamp()
