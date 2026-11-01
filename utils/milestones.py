import time
from datetime import datetime
from typing import Optional

from utils import db, guild_settings, scheduler

KEYS = {
    "channel": ("milestone_channel_id", None),
    "anniversary": ("milestone_anniversary", True),
    "levels": ("milestone_levels_enabled", True),
    "level_list": ("milestone_levels", [10, 25, 50, 75, 100]),
    "welcomeback": ("milestone_welcomeback", "off"),
    "away_days": ("milestone_away_days", 30),
}
WRITE_GAP = 6 * 3600
MODES = ("off", "channel", "dm")


async def get_config(guild_id: int) -> dict:
    out = {}
    for name, (key, default) in KEYS.items():
        out[name] = await guild_settings.get(guild_id, key, default)
    return out


async def set_config(guild_id: int, name: str, value) -> None:
    key, _ = KEYS[name]
    if value is None:
        await guild_settings.delete(guild_id, key)
    else:
        await guild_settings.set(guild_id, key, value)


async def last_seen(guild_id: int, user_id: int) -> Optional[float]:
    row = await db.raw_fetchone("SELECT last_seen FROM member_seen WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    return float(row["last_seen"]) if row else None


async def touch(guild_id: int, user_id: int, now: float) -> None:
    await db.raw_execute(
        "INSERT INTO member_seen (guild_id, user_id, last_seen) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET last_seen=excluded.last_seen",
        (guild_id, user_id, now))


async def local_now(guild_id: int) -> datetime:
    cfg = await scheduler.get_config(guild_id)
    tz = scheduler.parse_tz(cfg["timezone"]) or scheduler.parse_tz("UTC")
    return datetime.now(tz)


async def anniversary_done(guild_id: int) -> Optional[str]:
    return await db.get("milestone_anniversary", str(guild_id))


async def mark_anniversary(guild_id: int, day: str) -> None:
    await db.set("milestone_anniversary", str(guild_id), day)


def anniversaries(members, today: str) -> list[tuple[int, int]]:
    month_day = today[5:]
    year = int(today[:4])
    out = []
    for member in members:
        joined = getattr(member, "joined_at", None)
        if member.bot or joined is None:
            continue
        years = year - joined.year
        if years >= 1 and joined.strftime("%m-%d") == month_day:
            out.append((member.id, years))
    out.sort(key=lambda item: -item[1])
    return out


def parse_levels(values: list[str]) -> Optional[list[int]]:
    try:
        levels = sorted({int(v) for v in values})
    except ValueError:
        return None
    if not levels or any(not 1 <= n <= 1000 for n in levels) or len(levels) > 20:
        return None
    return levels


async def away_digest(guild, since: float) -> list[str]:
    joined = sum(1 for m in guild.members if not m.bot and m.joined_at is not None and m.joined_at.timestamp() > since)
    lines = []
    if joined:
        lines.append(f"{joined} new member{'s' if joined != 1 else ''} joined")
    events = [e for e in await scheduler.upcoming(guild.id, 3) if e["starts_at"] <= time.time() + 7 * 86400]
    for event in events:
        lines.append(f"Event: **{event['title']}** <t:{int(event['starts_at'])}:R>")
    return lines
