import re
import secrets
import time
from datetime import tzinfo
from typing import Optional

import config
from utils import db, scheduler

DURATION_TOKEN = re.compile(r"^\d+[a-z]+$")


async def get_timezone(user_id: int) -> tuple[str, tzinfo]:
    row = await db.raw_fetchone("SELECT tz FROM user_timezones WHERE user_id=?", (user_id,))
    name = row["tz"] if row else "UTC"
    return name, scheduler.parse_tz(name) or scheduler.parse_tz("UTC")


async def set_timezone(user_id: int, name: str) -> bool:
    if scheduler.parse_tz(name) is None:
        return False
    await db.raw_execute(
        "INSERT INTO user_timezones (user_id, tz) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET tz=excluded.tz",
        (user_id, name.strip()))
    return True


def split_when(text: str, now: float, tz: tzinfo) -> tuple[Optional[float], str]:
    text = text.strip()
    if "|" in text:
        head, _, tail = text.partition("|")
        return scheduler.parse_when(head, now, tz), tail.strip()
    tokens = text.split()
    index = 1 if tokens and tokens[0].lower() == "in" else 0
    start = index
    while index < len(tokens) and DURATION_TOKEN.match(tokens[index].lower()):
        index += 1
    if index > start:
        due = scheduler.parse_when(" ".join(tokens[:index]), now, tz)
        if due is not None:
            return due, " ".join(tokens[index:]).strip()
    for size in range(1, min(len(tokens), 6) + 1):
        due = scheduler.parse_when(" ".join(tokens[:size]), now, tz)
        if due is not None:
            return due, " ".join(tokens[size:]).strip()
    return None, text


def parse_interval(text: str) -> Optional[int]:
    parts = re.findall(r"(\d+)\s*([a-z]+)", text.lower())
    if not parts or not all(unit in scheduler.UNITS for _, unit in parts):
        return None
    return sum(int(amount) * scheduler.UNITS[unit] for amount, unit in parts) or None


def split_interval(text: str) -> tuple[Optional[int], str]:
    tokens = text.split()
    index = 0
    while index < len(tokens) and DURATION_TOKEN.match(tokens[index].lower()):
        index += 1
    if index == 0:
        return None, text
    return parse_interval(" ".join(tokens[:index])), " ".join(tokens[index:]).strip()


async def count(user_id: int) -> int:
    row = await db.raw_fetchone("SELECT COUNT(*) AS n FROM reminders WHERE user_id=?", (user_id,))
    return int(row["n"])


async def add(user_id: int, guild_id: int, channel_id: int, message: str, due_at: float, repeat: int = 0) -> dict:
    reminder_id = secrets.token_hex(2)
    while await db.raw_fetchone("SELECT 1 FROM reminders WHERE reminder_id=?", (reminder_id,)):
        reminder_id = secrets.token_hex(2)
    await db.raw_execute(
        "INSERT INTO reminders (reminder_id, user_id, guild_id, channel_id, message, created_at, due_at, repeat_seconds) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (reminder_id, user_id, guild_id, channel_id, message[:config.REMINDER_TEXT_MAX], time.time(), due_at, repeat))
    return {"reminder_id": reminder_id, "due_at": due_at, "message": message[:config.REMINDER_TEXT_MAX], "repeat_seconds": repeat}


async def of(user_id: int) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM reminders WHERE user_id=? ORDER BY due_at", (user_id,))
    return [dict(r) for r in rows]


async def remove(user_id: int, reminder_id: str) -> bool:
    cursor = await db.raw_execute("DELETE FROM reminders WHERE user_id=? AND reminder_id=?", (user_id, reminder_id.lower()))
    return getattr(cursor, "rowcount", 0) > 0


async def clear(user_id: int) -> int:
    cursor = await db.raw_execute("DELETE FROM reminders WHERE user_id=?", (user_id,))
    return getattr(cursor, "rowcount", 0)


async def due(now: float, limit: int = 50) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM reminders WHERE due_at<=? ORDER BY due_at LIMIT ?", (now, limit))
    return [dict(r) for r in rows]


async def advance(reminder: dict, now: float) -> None:
    if reminder["repeat_seconds"] > 0:
        next_due = reminder["due_at"] + reminder["repeat_seconds"]
        while next_due <= now:
            next_due += reminder["repeat_seconds"]
        await db.raw_execute("UPDATE reminders SET due_at=? WHERE reminder_id=?", (next_due, reminder["reminder_id"]))
    else:
        await db.raw_execute("DELETE FROM reminders WHERE reminder_id=?", (reminder["reminder_id"],))


async def has_timezone(user_id: int) -> bool:
    return await db.raw_fetchone("SELECT 1 FROM user_timezones WHERE user_id=?", (user_id,)) is not None
